# Demo Runbook

Use this for the Requirements & Design presentation (2026-11-10) and any supervisor demo. It assumes the
Windows setup from [INSTALLATION_MANUAL.md](INSTALLATION_MANUAL.md).

> The default build uses the **mock adapter**. Say so at the start. The demo proves the pipeline, the review
> contract and the export — not model accuracy. The real `videojev` adapter (VideoJev-4B) is available on a GPU
> worker (see "Real model path" below) but is not validated on product footage; do not claim accuracy.

## 1. Pre-flight (10 minutes before)

```powershell
# terminal 1 — API
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000

# terminal 2 — worker
cd backend
..\.venv\Scripts\python.exe -m app.worker --loop

# terminal 3 — checks
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
Invoke-RestMethod http://127.0.0.1:8000/api/v1/system/media
```

Checklist:

- [ ] Browser at <http://127.0.0.1:8000> shows the projects screen
- [ ] `data/` is writable, disk free > 2 GB
- [ ] A demo video exists locally (≤ 2 min is enough; have a 10+ min file for the long-video claim only if it was validated)
- [ ] Worker shows "worker started" in its log
- [ ] No token is required (or the token is entered in the UI)

## 2. Plan A — live path (6–8 minutes)

1. **Create project** "Demo — street interviews". Point at the stats tiles (all zero).
2. **Add action**: name `person waves`, description *"a person raises their right hand and waves at the
   camera, upper body visible"*. Explain this exact text goes to the model.
3. **Upload** the short video. Show the progress bar and the resulting duration/resolution. Mention the
   server-side checks (signature, size, duration, ffmpeg probe).
4. **Start processing** with the mock adapter. Show that the request returns immediately and the job goes
   `queued → running → succeeded` via polling. If the worker is stopped, show the queued state and explain
   the separation of concerns (optional).
5. Open **Review**. Play the source video, seek by selecting a candidate, play the extracted clip.
6. Label one candidate **true positive** with a corrected end time; label another **false positive**. Leave a
   third unreviewed on purpose.
7. Show the counters: reviewed vs **unreviewed** — explain that unreviewed is not negative.
8. **Export** (do not include unreviewed), wait for the export job, download the ZIP.
9. Open the ZIP: `manifest.json` (proposal/preview/corrected/final), `labels.csv`, a clip that plays.
   Show `provenance.mock = true`.

### Real model path (optional, GPU worker)

Start the worker as in [INSTALLATION_MANUAL.md](INSTALLATION_MANUAL.md) §5.1 (`VLM_VLM_ADAPTER=videojev`,
`VLM_VIDEOJEV_CONFIG=video_grounding/configs/rtx3070.yaml` on an 8 GB laptop), then run steps 1-9 with a short clip.
Expect minutes per video on 8 GB, no MOCK banner, `provenance.mock = false`, and 0..n candidates per video. Run it
once before presenting; the real-model smoke (`scripts/smoke_videojev.py`) is still pending on the project laptop.

## 3. Plan B — prepared fallback

If the live flow fails (worker crash, ffmpeg issue, browser problem):

- Show `docs/evidence/smoke-e2e-20261105-170733.json` — 26/26 checks with the real pipeline.
- Play the pre-exported `dataset.zip` from the last successful run (keep one locally, never commit footage).
- Show the API docs page and the test output:
  `.\.venv\Scripts\python.exe -m pytest backend -q` → 56 passed.

Do **not** improvise a claim that the demo worked. State what failed and what the evidence shows.

## 4. Recovery steps

| Symptom | Action |
|---|---|
| Job stuck queued | Start/restart the worker; check its terminal for errors |
| Upload 422 | Try the known-good demo file; check `/api/v1/system/media` |
| Export not ready | Wait for the worker; check job status and `error_message` |
| Page blank | Rebuild frontend (`npm run build`) and refresh; check uvicorn is serving `/` |
| 401 | Token is configured; enter it in the UI |

## 5. Presenter allocation

Fill with real names only when the team supplies them:

| Segment | Presenter | Backup |
|---|---|---|
| Problem and scope | TBD | TBD |
| Requirements and design | TBD | TBD |
| Live demo | TBD | TBD |
| Evidence and plan | TBD | TBD |

## 6. Questions to expect

- *"Is that a real model?"* → Not in the mock demo (labelled). A real model, VideoJev-4B, is integrated as the `videojev` adapter and was measured on a public benchmark (Charades-STA) only, below target; validation on product footage is pending.
- *"Why 8 GB?"* → The dev laptop's GPU; VideoJev-4B runs on it with CPU offload (about 0.66× the video duration on ~30 s Charades-STA videos); 7B bf16 does not fit.
- *"What if the model is wrong?"* → A human labels every candidate; the proposal is preserved separately.
- *"Can two reviewers work at once?"* → Yes at the API level; the queue is single-worker today.
