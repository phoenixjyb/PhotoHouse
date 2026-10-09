"""Read-only private-file checks for the selected recovery journal.

POSIX requires the current uid and owner-only mode. Windows checks the real
owner/DACL through Win32; chmod's read-only bit is not an access-control proof.
No ACL is changed, no subprocess is launched, and no Windows API loads on import.
References: https://learn.microsoft.com/en-us/windows/win32/fileio/file-security-and-access-rights
"""
from pathlib import Path
import os
import stat


def _refused():
    return ValueError('Private recovery storage unavailable')


def _acl_is_private(owner, current, entries):
    """Conservative DACL policy, independently testable without Windows handles."""
    privileged = {'S-1-5-18', 'S-1-5-32-544'}  # SYSTEM and local administrators.
    allowed = privileged | {current}
    if not current or owner not in allowed:
        return False
    for kind, flags, sid in entries:
        if kind == 1:  # ACCESS_DENIED_ACE cannot broaden access.
            continue
        if kind != 0:
            return False  # Conditional/object/callback ACEs need separate review.
        if sid in allowed:
            continue
        # OWNER RIGHTS applies to this object's actual owner, already proved
        # trusted above. Windows secure temporary directories use this ACE;
        # it does not name another user or an arbitrary creator placeholder.
        if sid == 'S-1-3-4':
            continue
        # CREATOR OWNER may exist solely as an inheritance template. The file's
        # effective ACE must resolve to the current user and is checked separately.
        if sid == 'S-1-3-0' and flags & 0x08:  # INHERIT_ONLY_ACE
            continue
        return False
    return True


def _windows_acl(path):
    import ctypes
    from ctypes import c_void_p, c_uint32, c_int, c_wchar_p, POINTER, byref

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    security = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = c_void_p
    kernel.CloseHandle.argtypes = [c_void_p]
    kernel.CloseHandle.restype = c_int
    kernel.LocalFree.argtypes = [c_void_p]
    kernel.LocalFree.restype = c_void_p
    security.OpenProcessToken.argtypes = [c_void_p, c_uint32, POINTER(c_void_p)]
    security.OpenProcessToken.restype = c_int
    security.GetTokenInformation.argtypes = [c_void_p, c_int, c_void_p, c_uint32, POINTER(c_uint32)]
    security.GetTokenInformation.restype = c_int
    security.GetNamedSecurityInfoW.argtypes = [c_wchar_p, c_int, c_uint32,
        POINTER(c_void_p), POINTER(c_void_p), POINTER(c_void_p), POINTER(c_void_p), POINTER(c_void_p)]
    security.GetNamedSecurityInfoW.restype = c_uint32
    security.IsValidSid.argtypes = [c_void_p]
    security.IsValidSid.restype = c_int
    security.GetLengthSid.argtypes = [c_void_p]
    security.GetLengthSid.restype = c_uint32
    security.ConvertSidToStringSidW.argtypes = [c_void_p, POINTER(c_wchar_p)]
    security.ConvertSidToStringSidW.restype = c_int
    security.IsValidAcl.argtypes = [c_void_p]
    security.IsValidAcl.restype = c_int
    security.GetAclInformation.argtypes = [c_void_p, c_void_p, c_uint32, c_int]
    security.GetAclInformation.restype = c_int
    security.GetAce.argtypes = [c_void_p, c_uint32, POINTER(c_void_p)]
    security.GetAce.restype = c_int

    def sid_text(pointer, available=None):
        if not pointer or not security.IsValidSid(pointer):
            raise _refused()
        length = security.GetLengthSid(pointer)
        if not 8 <= length <= 68 or (available is not None and length > available):
            raise _refused()
        value = c_wchar_p()
        if not security.ConvertSidToStringSidW(pointer, byref(value)):
            raise _refused()
        try:
            result = value.value
            if not result or len(result) > 200:
                raise _refused()
            return result
        finally:
            kernel.LocalFree(ctypes.cast(value, c_void_p))

    token, descriptor = c_void_p(), c_void_p()
    try:
        if not security.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, byref(token)):  # TOKEN_QUERY
            raise _refused()
        needed = c_uint32()
        security.GetTokenInformation(token, 1, None, 0, byref(needed))  # TokenUser
        if not ctypes.sizeof(c_void_p) <= needed.value <= 64 * 1024:
            raise _refused()
        buffer = ctypes.create_string_buffer(needed.value)
        if not security.GetTokenInformation(token, 1, buffer, needed.value, byref(needed)):
            raise _refused()
        current = sid_text(c_void_p.from_buffer(buffer).value)
        owner, dacl = c_void_p(), c_void_p()
        # SE_FILE_OBJECT, OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION
        if security.GetNamedSecurityInfoW(str(path), 1, 0x0001 | 0x0004,
                byref(owner), None, byref(dacl), None, byref(descriptor)) != 0:
            raise _refused()
        if not descriptor.value or not dacl.value or not security.IsValidAcl(dacl):
            raise _refused()  # A NULL DACL would grant everybody full access.
        info = (c_uint32 * 3)()
        if not security.GetAclInformation(dacl, info, ctypes.sizeof(info), 2):  # AclSizeInformation
            raise _refused()
        count, used, _ = info
        if count > 1024 or not 8 <= used <= 65535:
            raise _refused()
        entries = []
        for index in range(count):
            ace = c_void_p()
            if not security.GetAce(dacl, index, byref(ace)) or not ace.value:
                raise _refused()
            if not dacl.value + 8 <= ace.value <= dacl.value + used - 4:
                raise _refused()
            header = ctypes.string_at(ace, 4)
            size = int.from_bytes(header[2:4], 'little')
            if size < 16 or ace.value + size > dacl.value + used or header[0] not in (0, 1):
                raise _refused()
            entries.append((header[0], header[1], sid_text(ace.value + 8, size - 8)))
        if not _acl_is_private(sid_text(owner), current, entries):
            raise _refused()
    except (OSError, AttributeError, TypeError, OverflowError):
        raise _refused() from None
    finally:
        if descriptor.value:
            kernel.LocalFree(descriptor)
        if token.value:
            kernel.CloseHandle(token)


def _selected(path, directory):
    selected = Path(path)
    if not selected.is_absolute() or '..' in selected.parts:
        raise _refused()
    try:
        info = selected.lstat()
        if (not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
                or stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400):
            raise _refused()  # Reject Windows reparse points, including junctions.
        if not directory and info.st_nlink != 1:
            raise _refused()
        if os.name == 'nt':
            _windows_acl(selected)
        elif info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise _refused()
    except (OSError, TypeError):
        raise _refused() from None


def require_private_directory(path):
    _selected(path, True)


def require_private_file(path):
    _selected(path, False)


def sync_directory(path):
    """Sync the created entry on POSIX; Windows uses SQLite FULL and file fsync.

    Python offers no portable Windows directory fsync. Journal initialization
    must also be copied into the operator's independent recovery catalog before
    original intake is enabled; this helper does not claim power-loss recovery.
    """
    if os.name == 'nt':
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
