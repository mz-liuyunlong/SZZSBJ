from __future__ import annotations

import os
import tempfile
from pathlib import Path, PurePosixPath


class MediaStorageError(RuntimeError):
    """Safe storage error without filesystem details."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def validate_object_key(key: str) -> PurePosixPath:
    if not key or "\\" in key or "\x00" in key:
        raise MediaStorageError("MEDIA_OBJECT_KEY_INVALID")

    raw_parts = key.split("/")
    if key.startswith("/") or any(part in {"", ".", ".."} for part in raw_parts):
        raise MediaStorageError("MEDIA_OBJECT_KEY_INVALID")

    candidate = PurePosixPath(*raw_parts)
    if candidate.is_absolute():
        raise MediaStorageError("MEDIA_OBJECT_KEY_INVALID")
    return candidate


class FileSystemMediaStorage:
    """Atomic local storage adapter; cloud adapters can implement the same contract later."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def write(self, key: str, data: bytes) -> None:
        if not data:
            raise MediaStorageError("MEDIA_OBJECT_EMPTY")
        object_key = validate_object_key(key)
        target = (self.root / Path(*object_key.parts)).resolve()
        try:
            target.relative_to(self.root)
        except ValueError:
            raise MediaStorageError("MEDIA_OBJECT_KEY_INVALID") from None

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                dir=target.parent,
                prefix=".media-",
                suffix=".tmp",
            )
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary_name, target)
            except Exception:
                try:
                    os.unlink(temporary_name)
                except FileNotFoundError:
                    pass
                raise
        except OSError:
            raise MediaStorageError("MEDIA_STORAGE_WRITE_FAILED") from None

    def path_for(self, key: str) -> Path:
        object_key = validate_object_key(key)
        target = (self.root / Path(*object_key.parts)).resolve()
        try:
            target.relative_to(self.root)
        except ValueError:
            raise MediaStorageError("MEDIA_OBJECT_KEY_INVALID") from None
        return target
