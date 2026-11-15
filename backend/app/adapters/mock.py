"""Deterministic mock adapter used for the Sprint 2 vertical slice.

It is *explicitly* a mock: it never looks at pixels.  It exists so that the
whole asynchronous pipeline (queue -> worker -> candidates -> clips -> review ->
export) can be built and tested before real inference is wired in.  Candidates it
produces are labelled ``provenance=mock`` in the export manifest and flagged in
the UI.
"""

from __future__ import annotations

import hashlib
import random

from . import AdapterError, ProposalRequest, ProposedInterval


class MockTemporalAdapter:
    name = "mock"
    version = "1.0.0"
    requires_gpu = False

    def __init__(self, seed_salt: str = "vlm-annotate-mock-v1") -> None:
        self._salt = seed_salt

    def is_available(self) -> bool:
        return True

    def propose(self, request: ProposalRequest) -> list[ProposedInterval]:
        duration = float(request.duration_seconds)
        if duration <= request.min_duration_seconds:
            raise AdapterError(
                f"video is too short ({duration:.2f}s) for the minimum candidate duration"
            )

        seed_material = f"{self._salt}|{request.action_text}|{round(duration, 3)}"
        rng = random.Random(hashlib.sha256(seed_material.encode("utf-8")).digest())

        count = min(request.max_candidates, rng.randint(3, 6))
        count = max(1, count)
        slot = duration / count
        intervals: list[ProposedInterval] = []

        for index in range(count):
            slot_start = index * slot
            longest = min(request.max_duration_seconds, slot * 0.7)
            shortest = min(request.min_duration_seconds, longest)
            length = rng.uniform(shortest, longest) if longest > shortest else longest
            latest_start = slot_start + max(0.0, slot - length)
            start = (
                rng.uniform(slot_start, latest_start) if latest_start > slot_start else slot_start
            )
            end = min(duration, start + length)
            start = min(start, max(0.0, end - 0.5))
            if end - start < 0.5:
                continue
            score = round(0.95 - index * 0.07 + rng.uniform(-0.02, 0.02), 3)
            intervals.append(
                ProposedInterval(
                    start_seconds=round(start, 3),
                    end_seconds=round(end, 3),
                    score=max(0.0, min(1.0, score)),
                    notes=(
                        f"MOCK PROPOSAL — no video pixels were analysed. slot={index + 1}/{count}"
                    ),
                )
            )

        if not intervals:
            raise AdapterError("mock adapter produced no usable interval")
        return intervals
