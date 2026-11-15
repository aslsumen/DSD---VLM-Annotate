"""HTTP range responses for source videos and clips (needed for seeking)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from fastapi import Request
from fastapi.responses import StreamingResponse

from ..errors import ApiError

CHUNK_SIZE = 256 * 1024
_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def _iter_file(path: Path, start: int, length: int) -> Iterator[bytes]:
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = length
        while remaining > 0:
            chunk = handle.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def range_file_response(
    path: Path,
    request: Request,
    *,
    media_type: str,
    filename: str | None = None,
    attachment: bool = False,
) -> StreamingResponse:
    if not path.is_file():
        raise ApiError(404, "FILE_NOT_FOUND", "the stored media file is missing")

    size = path.stat().st_size
    range_header = request.headers.get("range")
    start, end = 0, max(0, size - 1)
    status_code = 200

    if range_header:
        match = _RANGE_RE.match(range_header.strip())
        if not match:
            raise ApiError(
                416, "INVALID_RANGE", "only single 'bytes=start-end' ranges are supported"
            )
        raw_start, raw_end = match.groups()
        if raw_start:
            start = int(raw_start)
            end = int(raw_end) if raw_end else size - 1
        elif raw_end:
            suffix = int(raw_end)
            start = max(0, size - suffix)
            end = size - 1
        if start >= size or start > end:
            raise ApiError(
                416,
                "RANGE_NOT_SATISFIABLE",
                "requested range is outside the file",
                {"size": size},
            )
        end = min(end, size - 1)
        status_code = 206

    length = end - start + 1
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Cache-Control": "private, max-age=60",
    }
    if filename:
        disposition = "attachment" if attachment else "inline"
        safe_name = filename.replace('"', "")
        headers["Content-Disposition"] = f'{disposition}; filename="{safe_name}"'
    if status_code == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    return StreamingResponse(
        _iter_file(path, start, length),
        status_code=status_code,
        media_type=media_type,
        headers=headers,
    )
