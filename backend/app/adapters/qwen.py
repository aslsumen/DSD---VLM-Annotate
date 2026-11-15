"""Qwen2.5-VL adapter skeleton (NOT WIRED — Sprint 2 feasibility only).

Status: **stub**.  It is registered so the UI/API can show the planned adapter
and so the provenance fields have a real target, but :meth:`is_available` returns
False and :meth:`propose` raises :class:`AdapterUnavailable`.

Why it is not implemented yet (evidence in docs/MODEL_EVALUATION.md):
  * torch + transformers + ~6-16 GB of weights are not installed; the project
    laptop has an 8 GB RTX 4060, so 7B in bf16 does not fit and a 2-4B model or
    4-bit quantisation must be chosen deliberately.
  * The verified input path is ``qwen_vl_utils.process_vision_info(...,
    return_video_kwargs=True)`` and ``processor(..., fps=fps)``; Qwen2.5-VL uses
    frame-rate information to align frames to absolute time.
  * A 10-30 minute video cannot be fed in one pass; the planned design is
    windowed inference (fixed-length chunks, uniformly sampled frames, fps in
    the processor call) followed by interval merging/deduplication.

Enable it only after adding the optional dependency group and downloading the
checkpoint; keep :class:`MockTemporalAdapter` as the CI default.
"""

from __future__ import annotations

from . import (
    AdapterUnavailable,
    ProposalRequest,
    ProposedInterval,
)

_MODEL_ID = "Qwen/Qwen2.5-VL-7B-Instruct"  # apache-2.0 (7B); the 3B is qwen-research


class Qwen25VLAdapter:
    name = "qwen2.5-vl"
    version = "0.0.1-stub"
    requires_gpu = True

    def __init__(self, model_id: str = _MODEL_ID) -> None:
        self.model_id = model_id

    def is_available(self) -> bool:
        try:
            import qwen_vl_utils  # noqa: F401
            import torch  # noqa: F401
            import transformers  # noqa: F401
        except Exception:
            return False
        return True

    def propose(self, request: ProposalRequest) -> list[ProposedInterval]:
        raise AdapterUnavailable(
            "qwen2.5-vl adapter is not wired yet: install the `vlm` extra "
            "(torch/transformers/qwen-vl-utils), download the checkpoint and implement "
            "windowed inference. Use the mock adapter for the Sprint 2 slice."
        )
