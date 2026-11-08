"""Private, encrypted file storage.

Files are encrypted with Fernet before being written. The default backend is the local
filesystem (mount a persistent volume in production). The interface is intentionally small
so an object-storage backend (S3, GCS, Supabase Storage) can be swapped in.
"""
import re
import shutil
import uuid
from pathlib import Path

from ..config import get_settings
from ..security import decrypt_bytes, encrypt_bytes

_KEY_RE = re.compile(r"^[0-9]+/[0-9a-f]{32}\.[a-z0-9]{1,8}$")


def _root() -> Path:
    return get_settings().storage_dir


def _path_for(key: str) -> Path:
    if not _KEY_RE.match(key):
        raise ValueError("Invalid storage key")
    return _root() / key


def save(user_id: int, data: bytes, ext: str) -> str:
    ext = re.sub(r"[^a-z0-9]", "", ext.lower())[:8] or "bin"
    key = f"{user_id}/{uuid.uuid4().hex}.{ext}"
    path = _path_for(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encrypt_bytes(data))
    return key


def load(key: str) -> bytes:
    return decrypt_bytes(_path_for(key).read_bytes())


def delete(key: str) -> None:
    if not key:
        return
    try:
        _path_for(key).unlink(missing_ok=True)
    except ValueError:
        pass


def delete_user(user_id: int) -> None:
    shutil.rmtree(_root() / str(int(user_id)), ignore_errors=True)
