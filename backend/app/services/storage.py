"""Safe local media storage.

Every uploaded file gets a generated storage key; the user-supplied filename is
kept only as metadata.  All path construction goes through :meth:`LocalStorage.path_for`
which rejects absolute paths and traversal segments.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

CHUNK_SIZE = 1024 * 1024


class StorageError(Exception):
    pass


class StorageBackend(Protocol):
    """Boundary for a future S3/object-storage implementation."""

    def save_stream(
        self, stream: BinaryIO, *, subdir: str, suffix: str, max_bytes: int
    ) -> StoredFile: ...

    def path_for(self, key: str) -> Path: ...

    def delete(self, key: str) -> None: ...


@dataclass(frozen=True)
class StoredFile:
    key: str
    size_bytes: int
    sha256: str


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    # -- public API ----------------------------------------------------
    def save_stream(
        self, stream: BinaryIO, *, subdir: str, suffix: str, max_bytes: int
    ) -> StoredFile:
        if not suffix.startswith(".") or len(suffix) > 10:
            raise StorageError(f"invalid suffix: {suffix!r}")
        safe_subdir = self._safe_subdir(subdir)
        key = f"{safe_subdir}/{uuid.uuid4().hex}{suffix.lower()}"
        final_path = self.path_for(key)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = final_path.with_suffix(final_path.suffix + ".part")

        digest = hashlib.sha256()
        size = 0
        try:
            with temp_path.open("wb") as out:
                while True:
                    chunk = stream.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        raise StorageError(f"upload exceeds the {max_bytes} byte limit")
                    digest.update(chunk)
                    out.write(chunk)
            os.replace(temp_path, final_path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
        return StoredFile(key=key, size_bytes=size, sha256=digest.hexdigest())

    def path_for(self, key: str) -> Path:
        if not key or key.startswith(("/", "\\")) or ":" in key:
            raise StorageError("storage key must be a relative path")
        candidate = (self.root / key).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise StorageError("storage key escapes the storage root") from exc
        return candidate

    def exists(self, key: str) -> bool:
        try:
            return self.path_for(key).is_file()
        except StorageError:
            return False

    def size(self, key: str) -> int:
        return self.path_for(key).stat().st_size

    def open(self, key: str) -> BinaryIO:
        return self.path_for(key).open("rb")

    def delete(self, key: str) -> None:
        try:
            self.path_for(key).unlink(missing_ok=True)
        except StorageError:
            return

    def copy_into(self, key: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.path_for(key), destination)

    def _safe_subdir(self, subdir: str) -> str:
        if not subdir or subdir.startswith(("/", "\\")) or ".." in Path(subdir).parts:
            raise StorageError(f"invalid subdirectory: {subdir!r}")
        return subdir.strip("/\\")
