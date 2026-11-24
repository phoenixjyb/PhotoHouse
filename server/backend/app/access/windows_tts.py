"""Bounded per-request Windows System.Speech synthesis child.

Request text and tokens travel only on pipes.  Each call owns one PowerShell
child, and the child writes its WAV to a capped in-memory stream.
"""
from __future__ import annotations

import base64
import binascii
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import threading
import time

from .assistant_speech import MAX_WAV_BYTES, valid_reply_wav
from .private_storage import require_private_file, stable_stat_identity

MAX_TEXT_BYTES = 600
MAX_FORM_BYTES = 2048
MAX_TOKEN_BYTES = 512
MAX_VOICE_NAME_BYTES = 256
MAX_CHILD_SECONDS = 30.0
MAX_CHILD_STDOUT = (MAX_WAV_BYTES * 4 // 3) + 1024
_TOKEN = re.compile(r'\A[A-Za-z0-9_-]{32,256}\Z', re.ASCII)


class TtsFailure(RuntimeError):
    """Sanitized child/provider failure."""


class TtsBusy(TtsFailure):
    """A synthesis request is already active."""


# This fixed command contains no family text, token or configurable command.
# The only per-request values arrive as bounded UTF-8 JSON on stdin.
_POWERSHELL = r'''
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -TypeDefinition @'
using System;
using System.IO;
public sealed class PhotoHouseCappedStream : MemoryStream {
    private readonly long limit;
    public PhotoHouseCappedStream(long maxBytes) { limit = maxBytes; }
    private void Check(long end) { if (end < 0 || end > limit) throw new InvalidOperationException(); }
    public override void Write(byte[] buffer, int offset, int count) {
        Check(Position + count); base.Write(buffer, offset, count);
    }
    public override void WriteByte(byte value) { Check(Position + 1); base.WriteByte(value); }
    public override void SetLength(long value) { Check(value); base.SetLength(value); }
}
'@ -ErrorAction Stop | Out-Null
Add-Type -AssemblyName System.Speech -ErrorAction Stop
function Emit([string]$json, [int]$code) {
    [Console]::Out.WriteLine($json)
    exit $code
}
try {
    $raw = [Console]::In.ReadToEnd()
    if ([Text.Encoding]::UTF8.GetByteCount($raw) -gt 4096) { Emit '{"success":false,"error":"invalid_request"}' 2 }
    $r = ConvertFrom-Json -InputObject $raw -ErrorAction Stop
    if ($r.operation -ceq 'voices') {
        $keys = @($r.PSObject.Properties.Name)
        $allowed = @('operation','zh_voice','en_voice')
        if (@($keys | Where-Object { $_ -cnotin $allowed }).Count -ne 0) {
            Emit '{"success":false,"error":"invalid_request"}' 2
        }
        $hasZh = $null -ne $r.PSObject.Properties['zh_voice']
        $hasEn = $null -ne $r.PSObject.Properties['en_voice']
        if ($hasZh -and ($r.zh_voice -isnot [string] -or !$r.zh_voice -or
            $r.zh_voice -cne $r.zh_voice.Trim() -or
            [Text.Encoding]::UTF8.GetByteCount($r.zh_voice) -gt 256 -or
            $r.zh_voice -match '[\x00-\x1f\x7f-\x9f]')) {
            Emit '{"success":false,"error":"invalid_request"}' 2
        }
        if ($hasEn -and ($r.en_voice -isnot [string] -or !$r.en_voice -or
            $r.en_voice -cne $r.en_voice.Trim() -or
            [Text.Encoding]::UTF8.GetByteCount($r.en_voice) -gt 256 -or
            $r.en_voice -match '[\x00-\x1f\x7f-\x9f]')) {
                Emit '{"success":false,"error":"invalid_request"}' 2
        }
        $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
        try {
            $found = @($s.GetInstalledVoices() | Where-Object {
                $_.Enabled -and $_.VoiceInfo.Culture.Name -cin @('zh-CN','en-US')
            } | Sort-Object { $_.VoiceInfo.Culture.Name }, { $_.VoiceInfo.Name })
            $zhVoices = @($found | Where-Object { $_.VoiceInfo.Culture.Name -ceq 'zh-CN' })
            $enVoices = @($found | Where-Object { $_.VoiceInfo.Culture.Name -ceq 'en-US' })
            if ($hasZh) {
                $selectedZh = @($zhVoices | Where-Object { $_.VoiceInfo.Name -ceq $r.zh_voice })
                if ($selectedZh.Count -ne 1) { Emit '{"success":false,"error":"voice_unavailable"}' 3 }
            }
            if ($hasEn) {
                $selectedEn = @($enVoices | Where-Object { $_.VoiceInfo.Name -ceq $r.en_voice })
                if ($selectedEn.Count -ne 1) { Emit '{"success":false,"error":"voice_unavailable"}' 3 }
            }
            $zh = if ($hasZh) { $true } else { $zhVoices.Count -gt 0 }
            $en = if ($hasEn) { $true } else { $enVoices.Count -gt 0 }
            Emit ('{{"success":true,"languages":[{0}{1}]}}' -f $(if($zh){'"zh"'}else{''}), $(if($en){if($zh){',"en"'}else{'"en"'}}else{''})) 0
        } finally { $s.Dispose() }
    }
    $keys = @($r.PSObject.Properties.Name)
    $hasVoiceName = $null -ne $r.PSObject.Properties['voice_name']
    $expected = @('operation','text','language','voice_speed','output_format')
    if ($hasVoiceName) { $expected += 'voice_name' }
    if ($keys.Count -ne $expected.Count -or
        @($keys | Where-Object { $_ -cnotin $expected }).Count -ne 0 -or
        @($expected | Where-Object { $_ -cnotin $keys }).Count -ne 0 -or
        $r.operation -cne 'synthesize' -or $r.language -cnotin @('zh','en') -or
        $r.voice_speed -cne '1.0' -or $r.output_format -cne 'wav' -or
        $r.text -isnot [string] -or !$r.text.Trim() -or
        [Text.Encoding]::UTF8.GetByteCount($r.text) -gt 600) {
        Emit '{"success":false,"error":"invalid_request"}' 2
    }
    if ($hasVoiceName -and ($r.voice_name -isnot [string] -or !$r.voice_name -or
        $r.voice_name -cne $r.voice_name.Trim() -or
        [Text.Encoding]::UTF8.GetByteCount($r.voice_name) -gt 256 -or
        $r.voice_name -match '[\x00-\x1f\x7f-\x9f]')) {
        Emit '{"success":false,"error":"invalid_request"}' 2
    }
    $culture = if ($r.language -ceq 'zh') { 'zh-CN' } else { 'en-US' }
    $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $stream = New-Object -TypeName PhotoHouseCappedStream -ArgumentList 2097152
    try {
        $voices = @($s.GetInstalledVoices() | Where-Object {
            $_.Enabled -and $_.VoiceInfo.Culture.Name -ceq $culture
        } | Sort-Object { $_.VoiceInfo.Name })
        if ($voices.Count -eq 0) { Emit '{"success":false,"error":"voice_unavailable"}' 3 }
        if ($hasVoiceName) {
            $selected = @($voices | Where-Object { $_.VoiceInfo.Name -ceq $r.voice_name })
            if ($selected.Count -eq 0) { Emit '{"success":false,"error":"voice_unavailable"}' 3 }
            if ($selected.Count -ne 1) { Emit '{"success":false,"error":"voice_ambiguous"}' 3 }
            $s.SelectVoice($selected[0].VoiceInfo.Name)
        } else {
            $s.SelectVoice($voices[0].VoiceInfo.Name)
        }
        $s.Rate = 0
        $s.SetOutputToWaveStream($stream)
        $s.Speak($r.text)
        if ($stream.Length -gt 2097152) { Emit '{"success":false,"error":"audio_limit"}' 4 }
        $encoded = [Convert]::ToBase64String($stream.ToArray())
        [Console]::Out.WriteLine('{"success":true,"audio_base64":"' + $encoded + '"}')
        exit 0
    } finally { $s.Dispose(); $stream.Dispose() }
} catch {
    Emit '{"success":false,"error":"synthesis_failed"}' 5
}
'''
_ENCODED_COMMAND = base64.b64encode(_POWERSHELL.encode('utf-16le')).decode('ascii')


def validate_voice_name(value):
    if (type(value) is not str or not value or value != value.strip() or
            len(value.encode('utf-8', errors='strict')) > MAX_VOICE_NAME_BYTES or
            any(ord(char) < 32 or 0x7f <= ord(char) < 0xa0 for char in value)):
        raise ValueError('Invalid Windows voice name')
    return value


def validate_request(fields):
    if type(fields) is not dict or set(fields) != {
            'text', 'language', 'voice_speed', 'output_format'}:
        raise ValueError('Invalid synthesis request')
    text = fields['text']
    if (type(text) is not str or type(fields['language']) is not str or
            type(fields['voice_speed']) is not str or type(fields['output_format']) is not str or
            not text.strip() or
            len(text.encode('utf-8', errors='strict')) > MAX_TEXT_BYTES or
            fields['language'] not in {'zh', 'en'} or
            fields['voice_speed'] != '1.0' or fields['output_format'] != 'wav'):
        raise ValueError('Invalid synthesis request')
    return {'operation': 'synthesize', **fields}


def read_private_token(path: Path) -> str:
    """Read one direct, bounded token file; never include its contents in errors."""
    if (not isinstance(path, Path) or not path.is_absolute() or '..' in path.parts):
        raise ValueError('Private token file required')
    try:
        if os.name == 'nt':
            # Refuse junctions/symlinks anywhere in the selected path. The
            # leaf ACL checker below validates the file's effective DACL.
            for parent in reversed(path.parents):
                if parent == Path(parent.anchor):
                    continue
                info = parent.lstat()
                if not _safe_windows_directory(info):
                    raise ValueError('Private token file required')
        require_private_file(path)
        before = _identity(path.lstat())
        if before[2] < 32 or before[2] > MAX_TOKEN_BYTES:
            raise ValueError('Private token file required')
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
        if _identity(path.lstat()) != before:
            raise ValueError('Private token file required')
        fd = os.open(path, flags)
        try:
            require_private_file(path)
            opened = os.fstat(fd)
            if _identity(opened) != before:
                raise ValueError('Private token file required')
            raw = os.read(fd, MAX_TOKEN_BYTES + 1)
            require_private_file(path)
            after = os.fstat(fd)
            if (_identity(after) != before or _identity(path.lstat()) != before or
                    opened.st_ctime_ns != after.st_ctime_ns):
                raise ValueError('Private token file required')
        finally:
            os.close(fd)
    except (OSError, UnicodeError, ValueError):
        raise ValueError('Private token file required') from None
    try:
        token = raw.decode('ascii').strip()
    except UnicodeDecodeError:
        raise ValueError('Private token file required') from None
    if len(raw) > MAX_TOKEN_BYTES or not _TOKEN.fullmatch(token):
        raise ValueError('Private token file required')
    return token


def _identity(info):
    return stable_stat_identity(info) + (info.st_nlink,)


def _safe_windows_directory(info):
    """Check an lstat result without assuming it is a Path object."""
    return stat.S_ISDIR(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400


def valid_token(token):
    return type(token) is str and bool(_TOKEN.fullmatch(token))


def _powershell_path():
    system_root = os.environ.get('SystemRoot', r'C:\Windows')
    path = Path(system_root) / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'
    if os.name != 'nt' or not path.is_absolute():
        raise TtsFailure('Local speech unavailable')
    return path


class WindowsSystemSpeech:
    """One isolated PowerShell/System.Speech child per synthesis request."""

    def __init__(self, *, executable=None, timeout=24.0, zh_voice=None, en_voice=None,
                 popen=subprocess.Popen,
                 monotonic=time.monotonic, sleep=time.sleep):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= MAX_CHILD_SECONDS:
            raise ValueError('Invalid local speech timeout')
        self.executable = Path(executable) if executable is not None else None
        self.voices = {
            'zh': validate_voice_name(zh_voice) if zh_voice is not None else None,
            'en': validate_voice_name(en_voice) if en_voice is not None else None,
        }
        self.timeout, self._popen = float(timeout), popen
        self._monotonic, self._sleep = monotonic, sleep
        self._busy = threading.Lock()
        self._active_lock = threading.Lock()
        self._active = None
        self._cancel = None
        self._unhealthy = False

    def _require_healthy(self):
        with self._active_lock:
            if self._unhealthy:
                raise TtsFailure('Local speech unavailable')

    def _poison(self):
        with self._active_lock:
            self._unhealthy = True

    def _command(self):
        executable = self.executable or _powershell_path()
        if not executable.is_absolute():
            raise TtsFailure('Local speech unavailable')
        return [str(executable), '-NoLogo', '-NoProfile', '-NonInteractive',
                '-EncodedCommand', _ENCODED_COMMAND]

    def _run(self, request):
        self._require_healthy()
        payload = json.dumps(request, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        if len(payload) > 4096:
            raise TtsFailure('Local speech unavailable')
        terminal = False
        cleanup_ok = True
        try:
            process = self._popen(self._command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, shell=False, close_fds=True,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except (OSError, ValueError, TypeError):
            raise TtsFailure('Local speech unavailable') from None
        cancel = threading.Event()
        with self._active_lock:
            self._active, self._cancel = process, cancel
        output = bytearray()
        overflow = threading.Event()
        reader_error = threading.Event()

        def drain():
            try:
                while True:
                    part = process.stdout.read(8192)
                    if not part:
                        return
                    remaining = MAX_CHILD_STDOUT + 1 - len(output)
                    output.extend(part[:remaining])
                    if len(output) > MAX_CHILD_STDOUT:
                        overflow.set()
                        return
            except Exception:
                reader_error.set()

        reader = threading.Thread(target=drain, name='photohouse-tts-child-output', daemon=True)
        reader.start()
        started = self._monotonic()
        try:
            try:
                process.stdin.write(payload)
                process.stdin.close()
            except (OSError, ValueError):
                self._stop_child(process)
                raise TtsFailure('Local speech unavailable') from None
            while process.poll() is None:
                if cancel.is_set():
                    self._stop_child(process)
                    raise TtsFailure('Local speech cancelled')
                if overflow.is_set():
                    self._stop_child(process)
                    raise TtsFailure('Local speech unavailable')
                if self._monotonic() - started >= self.timeout:
                    self._stop_child(process)
                    raise TtsFailure('Local speech timed out')
                self._sleep(0.01)
            process.wait()
            terminal = process.poll() is not None
            reader.join(timeout=2)
            if reader.is_alive() or reader_error.is_set() or overflow.is_set() or process.returncode != 0:
                raise TtsFailure('Local speech unavailable')
            if len(output) > MAX_CHILD_STDOUT:
                raise TtsFailure('Local speech unavailable')
            return bytes(output)
        finally:
            if process.poll() is None and not self._stop_child(process):
                cleanup_ok = False
            else:
                terminal = process.poll() is not None
            reader.join(timeout=2)
            reader_stopped = not reader.is_alive()
            if not reader_stopped or not terminal:
                cleanup_ok = False
            # BufferedReader.close() can wait on the reader's internal lock.
            # Only close pipes after the child is terminal and the reader has
            # stopped; otherwise retain them with the owned process reference.
            if terminal and reader_stopped:
                for pipe in (process.stdin, process.stdout):
                    try:
                        if pipe is not None and not getattr(pipe, 'closed', False):
                            pipe.close()
                    except Exception:
                        cleanup_ok = False
            with self._active_lock:
                if not cleanup_ok:
                    self._unhealthy = True
                if cleanup_ok and self._active is process:
                    self._active, self._cancel = None, None
            if not cleanup_ok:
                raise TtsFailure('Local speech unavailable') from None

    def _stop_child(self, process):
        success = True
        try:
            if process.poll() is None:
                process.kill()
        except Exception:
            success = False
        try:
            process.wait(timeout=5)
        except Exception:
            success = False
        try:
            if process.poll() is None:
                success = False
        except Exception:
            success = False
        if not success:
            self._poison()
        return success

    def cancel_active(self):
        """Cancel only this adapter's current child; never searches/kills by name."""
        with self._active_lock:
            process, cancel = self._active, self._cancel
            if cancel is not None:
                cancel.set()
        if process is not None:
            # The owning synthesis thread observes the event, kills and waits;
            # this caller never races it with a second wait on the same child.
            try:
                if process.poll() is None:
                    process.kill()
            except Exception:
                pass

    def synthesize(self, fields):
        request = validate_request(fields)
        selected = self.voices[request['language']]
        if selected is not None:
            request['voice_name'] = selected
        self._require_healthy()
        if not self._busy.acquire(blocking=False):
            raise TtsBusy('Local speech busy')
        try:
            raw = self._run(request)
            decoded = _decode_child(raw)
            if not valid_reply_wav(decoded):
                raise TtsFailure('Local speech unavailable')
            return decoded
        finally:
            self._busy.release()

    def languages(self):
        self._require_healthy()
        if not self._busy.acquire(blocking=False):
            raise TtsBusy('Local speech busy')
        try:
            request = {'operation': 'voices'}
            if self.voices['zh'] is not None:
                request['zh_voice'] = self.voices['zh']
            if self.voices['en'] is not None:
                request['en_voice'] = self.voices['en']
            raw = self._run(request)
            value = _strict_json(raw)
            if (type(value) is not dict or set(value) != {'success', 'languages'} or
                    value['success'] is not True or type(value['languages']) is not list or
                    any(language not in {'zh', 'en'} for language in value['languages']) or
                    len(set(value['languages'])) != len(value['languages'])):
                raise TtsFailure('Local speech unavailable')
            languages = set(value['languages'])
            if any(name is not None and language not in languages
                   for language, name in self.voices.items()):
                raise TtsFailure('Local speech unavailable')
            return languages
        finally:
            self._busy.release()


def _strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate')
            result[key] = value
        return result
    try:
        return json.loads(raw.decode('utf-8', errors='strict'), object_pairs_hook=pairs,
                          parse_constant=lambda _value: (_ for _ in ()).throw(ValueError('constant')))
    except (UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        raise TtsFailure('Local speech unavailable') from None


def _decode_child(raw):
    value = _strict_json(raw)
    if type(value) is not dict or value.get('success') is not True or set(value) != {'success', 'audio_base64'}:
        raise TtsFailure('Local speech unavailable')
    encoded = value['audio_base64']
    if type(encoded) is not str or len(encoded) > MAX_CHILD_STDOUT:
        raise TtsFailure('Local speech unavailable')
    try:
        audio = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise TtsFailure('Local speech unavailable') from None
    if len(audio) > MAX_WAV_BYTES:
        raise TtsFailure('Local speech unavailable')
    return audio
