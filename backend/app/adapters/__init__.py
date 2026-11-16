"""Model adapter boundary.

Every VLM integration implements :class:`VLMAdapter` and returns normalized
:class:`ProposedInterval` objects.  Nothing model-specific leaks into the API,
the database or the UI: the worker only ever sees this contract.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


class AdapterError(Exception):
    """Base class for adapter failures.  Retryable by default (transient runtime)."""

    code = "ADAPTER_ERROR"
    retryable = True


class AdapterUnavailable(AdapterError):
    """The adapter cannot run in this environment (missing weights, deps, GPU)."""

    code = "ADAPTER_UNAVAILABLE"
    retryable = False


class InvalidProposal(AdapterError):
    """The model returned something that violates the internal schema."""

    code = "INVALID_MODEL_OUTPUT"
    retryable = True


@dataclass(frozen=True)
class ProposalRequest:
    video_path: Path
    duration_seconds: float
    action_text: str
    max_candidates: int
    min_duration_seconds: float
    max_duration_seconds: float
    params: Mapping[str, Any] = field(default_factory=dict)
    # Optional hooks for long-running adapters: a per-job directory that survives
    # retries of the same job (resumable engines) and a 0..1 progress callback.
    work_dir: Path | None = None
    progress: Callable[[float], None] | None = None


@dataclass(frozen=True)
class ProposedInterval:
    start_seconds: float
    end_seconds: float
    score: float = 0.0
    notes: str = ""


@runtime_checkable
class VLMAdapter(Protocol):
    name: str
    version: str
    requires_gpu: bool

    def is_available(self) -> bool: ...

    def propose(self, request: ProposalRequest) -> list[ProposedInterval]: ...
