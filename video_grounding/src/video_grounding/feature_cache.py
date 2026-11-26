"""Disk cache for VideoJev visual features: keyed by clip content + sampling parameters, never by prompt.

torch is imported lazily so importing this module needs no torch. Entries are `root[/subdir]/<key>.pt`; a read refreshes
the file's mtime, and eviction (global over every subdir of root) deletes the oldest mtime first (LRU)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _warn(msg: str) -> None:
    print(f"feature_cache: {msg}", file=sys.stderr)


class FeatureCache:
    def __init__(self, root: str | Path, max_bytes: int, subdir: str | None = None):
        # The byte cap covers all of root; subdir only picks this cache's own namespace (e.g. one per video).
        self.root, self.max_bytes = Path(root), max_bytes
        self.dir = self.root / subdir if subdir else self.root

    def get(self, key: str) -> dict | None:
        """Entry as {"features": cpu tensor, "device": str, "record": dict}, or None. A corrupt file is deleted.
        The tensor stays on the CPU here, so a CUDA OOM while moving it can never delete a valid entry."""
        path = self.dir / f"{key}.pt"
        if not path.is_file():
            return None
        import torch
        try:
            blob = torch.load(path, map_location="cpu", weights_only=True)
            hit = {"features": blob["features"], "device": blob["device"], "record": json.loads(blob["record"])}
            os.utime(path)  # mark recently used
            return hit
        except Exception as e:
            _warn(f"dropping unreadable entry {path.name}: {e!r}")
            path.unlink(missing_ok=True)
            return None

    def put(self, key: str, features, record: dict) -> None:
        """Best effort: a failed write (disk full, ...) must never fail a job."""
        tmp = self.dir / f"{key}.pt.{os.getpid()}.tmp"
        try:
            import torch
            self.dir.mkdir(parents=True, exist_ok=True)
            torch.save({"features": features.detach().to("cpu"), "device": str(features.device),
                        "record": json.dumps(record, default=float)}, tmp)
            os.replace(tmp, self.dir / f"{key}.pt")  # atomic: a killed process never leaves a half file
            self._evict()
        except Exception as e:
            _warn(f"put failed for {key[:12]}: {e!r}")
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    def _evict(self) -> None:
        # ponytail: full directory scan per put; fine for thousands of files, keep a running total if that matters
        files = []
        for p in self.root.rglob("*.pt"):
            try:
                st = p.stat()
            except FileNotFoundError:  # another worker process may share the dir
                continue
            files.append((st.st_mtime, st.st_size, p))
        total = sum(size for _, size, _ in files)
        for _, size, p in sorted(files):
            if total <= self.max_bytes:
                break
            try:
                p.unlink()
            except FileNotFoundError:
                pass
            total -= size
