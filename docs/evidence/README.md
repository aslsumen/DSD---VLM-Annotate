# Evidence

Machine-produced evidence for claims made in the documents and decks. Nothing here is hand-written output:
each file is the JSON result of a script that actually ran.

## Files

| File | Producer | What it proves |
|---|---|---|
| `smoke-e2e-20261105-170733.json` | `scripts/smoke_e2e.py` | 26/26 checks on a real 2-minute H.264/AAC video: upload, ffmpeg probe, async job via the real worker, candidate intervals in range, real clip extraction, clip decodability, annotation, async export, archive contents, corrected-boundary precedence, mock provenance |

Each run creates a new timestamped file; keep them all (they are cheap) and reference the one used in the
weekly report.

## How to reproduce

```powershell
.\.venv\Scripts\python.exe scripts\smoke_e2e.py
```

The script creates a synthetic video with ffmpeg (`testsrc` + `sine`), runs the API in-process, processes the
job with the real worker, labels a candidate, exports a ZIP and verifies it, then writes the JSON file.

## What this evidence does **not** prove

- Any model accuracy: candidate intervals come from the **mock adapter** (no pixels analysed).
- Behaviour on 10–30 minute real footage (only a 2-minute synthetic clip is used).
- UI behaviour: no browser automation is part of this script.
- Multi-user or concurrent-worker behaviour.

Those gaps are listed in [../TEST_PLAN.md](../TEST_PLAN.md) §6 and in the risk register.
