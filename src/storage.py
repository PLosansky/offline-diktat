"""User-data storage, independent of the read-only application directory."""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import tempfile
import time


def is_directory(path):
    """Use Windows directory attributes instead of pathlib's stat-based check.

    Some redirected/filtered corporate profiles allow file access but do not
    behave like an ordinary directory during Python's post-mkdir stat check.
    A regular file at the requested path must never be accepted as a directory.
    """
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        get_attributes = kernel32.GetFileAttributesW
        get_attributes.argtypes = [ctypes.c_wchar_p]
        get_attributes.restype = ctypes.c_uint32
        attributes = get_attributes(os.fspath(path))
        return attributes != 0xFFFFFFFF and bool(attributes & 0x10)
    return Path(path).is_dir()


def ensure_directory(path):
    path = Path(path)
    if is_directory(path):
        return path
    try:
        path.mkdir(parents=True, exist_ok=True)
    except FileExistsError:
        # A concurrent creator or a misleading pathlib stat result is harmless
        # only when Windows confirms that this really is a directory.
        if not is_directory(path):
            raise
    return path


def write_json(path, data):
    path = Path(path)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    ensure_directory(path.parent)
    temporary = None
    try:
        # Same directory / volume as the destination; never use the program
        # directory or a potentially redirected system TEMP directory.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         prefix=f".{path.name}.", suffix=".tmp",
                                         dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        for attempt in range(4):
            try:
                os.replace(temporary, path)
                break
            except PermissionError as exc:
                # A short Windows file-scanner lock can outlive close(). Never
                # truncate the old file and never retry persistent errors forever.
                if attempt == 3 or getattr(exc, "winerror", None) not in (5, 32, 33):
                    raise
                time.sleep(0.05 * (attempt + 1))
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                # Keep the original write error when security software blocks
                # deletion too. Never remove or truncate the existing settings.
                pass


def prepare_user_directory(path):
    """Check create/write/replace/delete with disposable names, not user files."""
    path = ensure_directory(path)
    probe = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".offline-diktat-check-", suffix=".json",
                                         dir=path, delete=False) as file:
            probe = Path(file.name)
        write_json(probe, {"storage_check": True})
    finally:
        if probe is not None:
            probe.unlink(missing_ok=True)
    return path
