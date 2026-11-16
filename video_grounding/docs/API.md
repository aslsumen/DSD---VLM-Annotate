# Python API

English | [简体中文](API.zh-CN.md)

The engine is a library. In the product, the backend worker calls it through `backend/app/adapters/videojev.py`: one job = one video × one action (one query), and the backend cuts preview clips itself, so the adapter sets `export.cut_clips=false`. Setup and the debugging CLI are in [USAGE.md](USAGE.md).

## Entry points (`video_grounding.scheduler`)

```python
run_scan(video: str, queries: list[Query], settings: Settings, out_dir: str | Path, *,
         video_info: VideoInfo | None = None, backend=None, job_id: str | None = None,
         keep_loaded: bool = False, verifier=None,
         progress: Callable[[float], None] | None = None) -> dict

resume(out_dir: str | Path, *, backend=None, video_info: VideoInfo | None = None,
       keep_loaded: bool = False, verifier=None,
       progress: Callable[[float], None] | None = None) -> dict

export(out_dir: str | Path, *, high: float | None = None, low: float | None = None) -> dict
```

- `Query(query_id, text)` is in `video_grounding.models`; `Settings` and `load_settings(path)` are in `video_grounding.settings`.
- `run_scan` starts a job in a new `out_dir`; `resume` continues an interrupted one (source fingerprint, model revision and config hash are checked; a mismatch raises `ResumeMismatch`); `export` re-fuses stored predictions with optional new thresholds and calls no model.
- All three return the `events.json` document (fields below). `backend` / `verifier` default to the ones named in settings; pass your own to reuse a loaded model across jobs together with `keep_loaded=True`.

### Progress

`progress(fraction)` is called on the calling thread with a value in [0, 1] that never decreases within one `run_scan` / `resume` call:

- coarse scan: `0.8 * done_windows / total_windows`, after every window (windows already done on resume count);
- refinement: `0.8 + 0.2 * finished_queries / total_queries`, after every query;
- `1.0` once `events.json` has been written.

An exception raised by the callback propagates out of `run_scan` / `resume`; use this to abort. Finished windows are stored, so `resume` continues from them.

## `events.json`

| Top-level field | Meaning |
|---|---|
| `job_id`, `video`, `video_duration_sec` | Job identity and source |
| `backend`, `model_id`, `model_revision` | Grounding backend and model identity |
| `scan_complete` | No permanently failed windows. This is not Gemini completion |
| `queries` | Per query: `query_id`, `query`, `warnings`, `scan_complete` |
| `events` | Retained events, including candidates that could not be verified |
| `coverage_gaps` | Permanently failed windows: `query_id`, `window_id`, `start_sec`, `end_sec`, `reason` |
| `rejected_events` | Only with Gemini enabled: Gemini-negative events, same shape as `events` |

Example event (illustrative values):

```json
{
  "event_id": "evt_0123456789ab", "query_id": "q1", "query": "A person opens a door",
  "event_start_sec": 12.5, "event_end_sec": 18.0, "clip_start_sec": 12.0, "clip_end_sec": 18.5,
  "complete": "likely", "needs_review": false, "review_reasons": [],
  "raw_score_max": 0.96, "alignment_status": "estimated",
  "evidence_window_ids": ["window_example"], "clip_path": "clips/evt_0123456789ab.mp4",
  "verdict": {"present": true, "p_present": 0.91, "model": "gemini-decision-1"}
}
```

- All `*_sec` fields are **global source-video seconds** (0 = first frame), not clip-local. In a clip player the event starts at `event_start_sec - clip_start_sec`.
- `event_*` are the predicted boundaries; `clip_*` add pre/post-roll, clamped to the video.
- `complete` is `likely|unknown`, a heuristic about boundary completeness.
- `raw_score_max` is an uncalibrated VideoJev score, not a probability. Events of one query are sorted by descending score, not chronologically.
- `alignment_status` is usually `exact|estimated|unknown`; keep `review_reasons` and query `warnings`, and tolerate new values.
- `verdict` is null or `{present, p_present, model}`; the cutoff is fixed at 0.5. With verification on, a failed call gives `verdict=null`, `needs_review=true` and `not_verified` in `review_reasons`.
- `clip_path` is relative to the job directory and null when `export.cut_clips=false`.
- Event IDs do not include the video identity; reference an event as `(job_id, event_id)`.
- A finished job can still have coverage gaps or unverified candidates: read `scan_complete`, `coverage_gaps`, `verdict` and `review_reasons` separately.
