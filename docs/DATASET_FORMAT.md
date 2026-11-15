# Dataset Format (export schema 1.0)

An export is a ZIP produced by the worker. It is designed so a third party can use the dataset **without**
the VLM Annotate database.

```text
vlm-annotate-project-<id>-<YYYYMMDD-HHMMSS>.zip
├── manifest.json
├── labels.csv
├── README.txt
└── clips/
    └── candidate_00001.mp4 ...
```

## 1. Units and precedence (normative)

- All times are **seconds**, floating point, relative to the **start of the source video**.
- Intervals are **half-open** `[start, end)`.
- Effective label interval: **`corrected` if present, else `proposal`** (`final` in the manifest).
- `preview` is only the padded window used for the clip, never the label.
- `verdict` is `true_positive`, `false_positive`, or — only when the export explicitly included
  unreviewed items — `unreviewed`.

## 2. `manifest.json`

```json
{
  "schema_version": "1.0",
  "exported_at": "2026-11-05T17:07:33+00:00",
  "project": {"id": 1, "name": "Smoke project"},
  "units": "seconds, source-video-relative, half-open [start, end)",
  "include_unreviewed": false,
  "item_count": 1,
  "items": [
    {
      "candidate_id": 1,
      "verdict": "true_positive",
      "review_state": "reviewed",
      "video": {
        "id": 1,
        "original_filename": "synthetic_2min.mp4",
        "duration_seconds": 120.0,
        "checksum_sha256": "…64 hex chars…"
      },
      "action": {
        "id": 1,
        "name": "person waves",
        "description": "a person waves at the camera with their right hand"
      },
      "job": {"id": 1, "adapter_name": "mock", "adapter_version": "1.0.0"},
      "proposal": {"start_seconds": 5.108, "end_seconds": 9.231, "score": 0.95},
      "preview": {"start_seconds": 4.108, "end_seconds": 10.231},
      "corrected": {"start_seconds": 5.608, "end_seconds": 8.608},
      "final": {"start_seconds": 5.608, "end_seconds": 8.608},
      "clip": {"file": "clips/candidate_00001.mp4", "status": "ready"},
      "note": "synthetic check",
      "reviewer": "smoke-script",
      "reviewed_at": "2026-11-05T17:07:33+00:00",
      "provenance": {
        "adapter": "mock",
        "adapter_version": "1.0.0",
        "mock": true,
        "proposal_clamped": false
      }
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `proposal` | Raw model output (after bound clamping), original source-relative seconds |
| `preview` | Window actually cut to `clip.file` |
| `corrected` | Human correction or `null` |
| `final` | Interval a consumer should train/evaluate on |
| `clip.status` | `ready` / `failed` / `pending`; `file` is `null` if no clip was copied |
| `provenance.mock` | **`true` means the intervals are not model predictions** |
| `provenance.proposal_clamped` | The model returned out-of-range boundaries that were clamped |
| `video.checksum_sha256` | SHA-256 of the uploaded source file, for traceability |

## 3. `labels.csv`

One row per exported item, UTF-8, comma-separated:

```csv
candidate_id,verdict,video_id,video_filename,action_name,start_seconds,end_seconds,proposal_start_seconds,proposal_end_seconds,score,clip_file,reviewer,reviewed_at,note
1,true_positive,1,synthetic_2min.mp4,person waves,5.608,8.608,5.108,9.231,0.95,clips/candidate_00001.mp4,smoke-script,2026-11-05T17:07:33+00:00,synthetic check
```

`start_seconds`/`end_seconds` are the **final** interval. Nuance (proposal vs correction) is preserved in the
manifest, so CSV consumers can choose the simple view without losing the audit trail.

## 4. Clips

- Container: MP4, H.264 video (scaled to max width 1280, even height) + AAC audio when the source has audio,
  `+faststart` for streaming.
- Encoded from the **preview** window, not from the final label, so a reviewer can see context.
- Filename: `clips/candidate_<zero-padded id>.mp4`.
- A failed clip is omitted; `clip.status` explains why.

## 5. `README.txt`

Mirrors the units and precedence rules and states how many items came from the mock adapter. It travels with
the dataset so the rules cannot be lost.

## 6. Validation checklist for consumers

1. `schema_version` is `1.0`.
2. For every item: `0 ≤ final.start < final.end ≤ video.duration_seconds`.
3. `final` equals `corrected` when `corrected` is non-null, otherwise `proposal`.
4. Every non-null `clip.file` exists in the archive and decodes.
5. If `provenance.mock` is true, do not present the dataset as model-labelled ground truth.

## 7. Versioning

Adding fields is backward-compatible; changing units, precedence or the `verdict` domain requires a new
`schema_version`. Planned additions: per-item frame timestamps, model confidence calibration, and an optional
COCO/ActivityNet adapter (Q-04).
