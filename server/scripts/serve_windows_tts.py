#!/usr/bin/env python3
"""Private loopback bridge to installed Windows System.Speech voices.

No request text or audio is written to disk or logged. The default invocation
prints a plan and neither reads the token file nor enumerates voices.
"""
from __future__ import annotations

import argparse
import asyncio
import hmac
import json
from pathlib import Path
import sys
from urllib.parse import parse_qsl

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'backend'
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.access.windows_tts import (  # noqa: E402
    MAX_FORM_BYTES, TtsBusy, TtsFailure, WindowsSystemSpeech, read_private_token,
    valid_reply_wav, valid_token,
)

HOST = '127.0.0.1'
PORT = 7350
PATH = '/speech'
PRIVATE_HEADERS = {'Cache-Control': 'no-store', 'Pragma': 'no-cache',
                   'X-Content-Type-Options': 'nosniff',
                   'Cross-Origin-Resource-Policy': 'same-origin'}


def _form_fields(body: bytes):
    try:
        pairs = parse_qsl(body.decode('ascii', errors='strict'), keep_blank_values=True,
            strict_parsing=True, encoding='utf-8', errors='strict', max_num_fields=4)
    except (UnicodeError, ValueError):
        raise HTTPException(400, 'Invalid synthesis request') from None
    if len(pairs) != 4 or len({key for key, _value in pairs}) != 4:
        raise HTTPException(400, 'Invalid synthesis request')
    fields = dict(pairs)
    if set(fields) != {'text', 'language', 'voice_speed', 'output_format'}:
        raise HTTPException(400, 'Invalid synthesis request')
    return fields


async def _read_form(request: Request):
    if request.scope.get('query_string'):
        raise HTTPException(400, 'Invalid synthesis request')
    content_types = request.headers.getlist('content-type')
    if (len(content_types) != 1 or content_types[0].strip().lower() !=
            'application/x-www-form-urlencoded' or request.headers.get('content-encoding') is not None):
        raise HTTPException(415, 'Form body required')
    lengths = request.headers.getlist('content-length')
    if len(lengths) > 1:
        raise HTTPException(400, 'Invalid synthesis request')
    if lengths:
        length = lengths[0]
        if len(length)>6 or not length.isascii() or not length.isdecimal() or int(length) > MAX_FORM_BYTES:
            raise HTTPException(413, 'Synthesis request too large')
    raw = bytearray()
    try:
        async with asyncio.timeout(5):
            async for chunk in request.stream():
                if len(raw) + len(chunk) > MAX_FORM_BYTES:
                    raise HTTPException(413, 'Synthesis request too large')
                raw.extend(chunk)
    except TimeoutError:
        raise HTTPException(408, 'Synthesis request timed out') from None
    if lengths and len(raw) != int(lengths[0]):
        raise HTTPException(400, 'Invalid synthesis request')
    return _form_fields(bytes(raw))


def create_app(*, token: str, synthesizer=None):
    if not valid_token(token):
        raise ValueError('Private TTS credential required')
    synthesizer = synthesizer or WindowsSystemSpeech()
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None, redirect_slashes=False)
    gate = asyncio.Lock()

    @app.exception_handler(HTTPException)
    async def safe_http_error(_request, error):
        return JSONResponse({'detail': error.detail}, status_code=error.status_code,
                            headers={**PRIVATE_HEADERS, **(error.headers or {})})

    @app.post('/speech')
    async def speech(request: Request):
        if request.headers.getlist('origin') or request.headers.getlist('sec-fetch-site'):
            raise HTTPException(403, 'Denied', headers=PRIVATE_HEADERS)
        authorization = request.headers.getlist('authorization')
        if (len(authorization) != 1 or len(authorization[0])>512 or
                not hmac.compare_digest(authorization[0].encode('utf-8'), ('Bearer ' + token).encode('ascii'))):
            raise HTTPException(403, 'Denied', headers=PRIVATE_HEADERS)
        fields = await _read_form(request)
        try:
            from app.access.windows_tts import validate_request
            validate_request(fields)
        except (ValueError, UnicodeError):
            raise HTTPException(400, 'Invalid synthesis request', headers=PRIVATE_HEADERS) from None
        if gate.locked():
            raise HTTPException(503, 'Local speech busy', headers=PRIVATE_HEADERS)
        await gate.acquire()
        task = asyncio.create_task(asyncio.to_thread(synthesizer.synthesize, fields))
        try:
            while not task.done():
                if await request.is_disconnected():
                    await asyncio.to_thread(synthesizer.cancel_active)
                    await asyncio.gather(task, return_exceptions=True)
                    raise HTTPException(499, 'Request ended', headers=PRIVATE_HEADERS)
                await asyncio.sleep(0.05)
            try:
                audio = task.result()
            except (TtsBusy, TtsFailure):
                raise HTTPException(503, 'Local speech unavailable', headers=PRIVATE_HEADERS) from None
            except Exception:
                raise HTTPException(503, 'Local speech unavailable', headers=PRIVATE_HEADERS) from None
            if not isinstance(audio, bytes) or not valid_reply_wav(audio):
                raise HTTPException(503, 'Local speech unavailable', headers=PRIVATE_HEADERS)
            return Response(content=audio, media_type='audio/wav', headers=PRIVATE_HEADERS)
        except asyncio.CancelledError:
            await asyncio.to_thread(synthesizer.cancel_active)
            await asyncio.gather(task, return_exceptions=True)
            raise
        finally:
            gate.release()

    return app


def _plan():
    print(json.dumps({'mode': 'plan', 'bind': HOST, 'port': PORT, 'path': PATH,
        'starts_listener': False, 'reads_token': False, 'enumerates_voices': False},
        separators=(',', ':')))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--check', action='store_true', help='Check token file only; no listener or child')
    modes.add_argument('--serve', action='store_true', help='Start the fixed loopback service')
    modes.add_argument('--qualify', action='store_true', help='Synthesize fixed synthetic test phrases')
    parser.add_argument('--token-file', type=Path,
        help='Private file containing the service bearer token; never printed')
    args = parser.parse_args(argv)
    if not (args.check or args.serve or args.qualify):
        if args.token_file is not None:
            parser.error('--token-file requires --check or --serve')
        return _plan()
    if args.qualify:
        if args.token_file is not None:
            parser.error('--token-file is not accepted with --qualify')
        try:
            synthesizer = WindowsSystemSpeech()
            languages = synthesizer.languages()
            outputs = {}
            for language, phrase in (('zh', '这是本地语音合成测试。'),
                                     ('en', 'This is a local speech synthesis test.')):
                if language in languages:
                    audio = synthesizer.synthesize({'text': phrase, 'language': language,
                        'voice_speed': '1.0', 'output_format': 'wav'})
                    outputs[language] = len(audio)
            print(json.dumps({'qualification': 'passed' if set(outputs) == {'zh', 'en'} else 'unavailable',
                'wav_bytes': outputs, 'saved_audio': False}, separators=(',', ':')))
            return 0 if set(outputs) == {'zh', 'en'} else 2
        except TtsFailure:
            print(json.dumps({'qualification': 'unavailable', 'saved_audio': False}), file=sys.stderr)
            return 2
    if args.token_file is None:
        parser.error('--token-file is required for --check and --serve')
    try:
        token = read_private_token(args.token_file)
    except ValueError:
        print('Private TTS token file unavailable', file=sys.stderr)
        return 2
    if args.check:
        print(json.dumps({'configuration': 'valid', 'listener_started': False,
                          'child_started': False, 'voices_enumerated': False}, separators=(',', ':')))
        return 0
    synthesizer = WindowsSystemSpeech()
    try:
        if synthesizer.languages() != {'zh', 'en'}:
            raise TtsFailure('Required local voices unavailable')
    except TtsFailure:
        print('Required local speech voices unavailable', file=sys.stderr)
        return 2
    import uvicorn
    uvicorn.run(create_app(token=token, synthesizer=synthesizer), host=HOST, port=PORT,
                workers=1, proxy_headers=False, access_log=False, server_header=False,
                limit_concurrency=8, timeout_keep_alive=5, timeout_graceful_shutdown=5,
                log_level='warning')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
