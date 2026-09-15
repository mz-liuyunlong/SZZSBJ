from pathlib import Path

import pytest

from app.modules.media_assets.storage import (
    FileSystemMediaStorage,
    MediaStorageError,
    validate_object_key,
)


def test_storage_writes_atomically_under_root(tmp_path: Path) -> None:
    storage = FileSystemMediaStorage(tmp_path)

    storage.write("images/ab/hash/thumbnail_128.webp", b"image")

    target = tmp_path / "images/ab/hash/thumbnail_128.webp"
    assert target.read_bytes() == b"image"


@pytest.mark.parametrize(
    "key",
    [
        "",
        "/absolute.webp",
        "../escape.webp",
        "images/../escape.webp",
        "./image.webp",
    ],
)
def test_object_key_rejects_traversal(key: str) -> None:
    with pytest.raises(MediaStorageError):
        validate_object_key(key)
