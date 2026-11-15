"""Storage safety tests: generated keys, traversal rejection, size limits."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from app.services.storage import LocalStorage, StorageError


@pytest.fixture()
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(tmp_path / "storage")


def test_save_stream_generates_key_and_checksum(storage: LocalStorage) -> None:
    stored = storage.save_stream(
        io.BytesIO(b"hello world"), subdir="videos/1", suffix=".mp4", max_bytes=1024
    )
    assert stored.key.startswith("videos/1/")
    assert stored.key.endswith(".mp4")
    assert stored.size_bytes == 11
    assert len(stored.sha256) == 64
    assert storage.path_for(stored.key).read_bytes() == b"hello world"


def test_save_stream_rejects_oversize_and_leaves_no_file(storage: LocalStorage) -> None:
    with pytest.raises(StorageError):
        storage.save_stream(io.BytesIO(b"x" * 100), subdir="videos", suffix=".mp4", max_bytes=10)
    leftovers = list(storage.root.rglob("*.part"))
    assert leftovers == []


@pytest.mark.parametrize(
    "bad_key",
    ["../escape.mp4", "..\\escape.mp4", "/etc/passwd", "C:\\Windows\\win.ini", "", "a/../../b"],
)
def test_path_for_rejects_traversal(storage: LocalStorage, bad_key: str) -> None:
    with pytest.raises(StorageError):
        storage.path_for(bad_key)


def test_path_for_accepts_nested_key(storage: LocalStorage) -> None:
    path = storage.path_for("clips/1-2-3.mp4")
    assert path.is_relative_to(storage.root)


def test_delete_is_idempotent(storage: LocalStorage) -> None:
    storage.delete("clips/missing.mp4")
    storage.delete("../../etc/passwd")
