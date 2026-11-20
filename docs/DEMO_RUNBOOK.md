# Demo Runbook

Use this for the Sprint 3 Alpha or a supervisor demo. The commands below use the Windows setup in
[INSTALLATION_MANUAL.md](INSTALLATION_MANUAL.md), which also covers macOS and Linux.

> The default build uses the **mock adapter**. Say so at the start. The demo proves the pipeline, the review
> contract and the export — not model accuracy. The real `videojev` adapter (VideoJev-4B) is available on a GPU
> worker (see "Real model path" below) but is not validated on product footage; do not claim accuracy.

## 1. Pre-flight (10 minutes before)

Build the UI from `frontend/` with `npm run build`. Use an isolated local demo database and storage
directory. Start both the API and worker with the same database and storage settings, with
`VLM_AUTH_REQUIRED=false`, `VLM_API_TOKEN` empty, and `VLM_VLM_ADAPTER=mock`.

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

- [ ] Browser at <http://127.0.0.1:8000> shows Datasets and the sidebar says **Development mode**
- [ ] Demo storage is writable and disk free > 2 GB
- [ ] A short local MP4 is available (a 30-second synthetic 720p clip works)
- [ ] Worker shows "worker started" in its log

## 2. Plan A — live path (6–8 minutes)

1. Select **New dataset**, enter a name, and create it.
2. Upload the short MP4 and check the resulting duration and ready state.
3. Open **New search**, describe the event in free text, select the `mock` model, and choose **Run search**.
4. Watch the search status update. To reliably show **Queued**, start the worker after the search is
   saved. With a short clip, the worker may finish between polls. Reload the search URL and confirm it still opens.
5. Choose **Review candidates**. Select a candidate, check that the full video seeks to its start, and play it.
6. Accept one candidate with a corrected timestamp and reject another if available. Select the **Accepted**
   filter, reload, and check that the saved decision remains. Return to the dataset and reopen the search.
7. For the export segment, use **Export → Download JSON** to show accepted annotations. The separate ZIP
   package can also demonstrate `manifest.json`, `labels.csv`, extracted clips, and `provenance.mock = true`.

### Real model path (optional, GPU worker)

Start the worker as in [INSTALLATION_MANUAL.md](INSTALLATION_MANUAL.md) §5.1 (`VLM_VLM_ADAPTER=videojev`,
`VLM_VIDEOJEV_CONFIG=video_grounding/configs/rtx3070.yaml` on an 8 GB laptop), then repeat Plan A with a
short clip using the `videojev` model.
Expect minutes per video on 8 GB, no MOCK banner, `provenance.mock = false`, and 0..n candidates per video. Run it
once before presenting; the real-model smoke (`scripts/smoke_videojev.py`) is still pending on the project laptop.

## 3. Plan B — prepared fallback

If the live flow fails (worker crash, ffmpeg issue, browser problem):

- Show the [Sprint 3 P0 verification](IMPLEMENTATION_LOG.md#2026-11-20--sprint-3-alpha-search-resilience)
  and the API/worker smoke evidence in `docs/evidence/`.
- Play the pre-exported `dataset.zip` from the last successful run (keep one locally, never commit footage).
- Show the API docs page and the test output recorded for the current build.

Do **not** improvise a claim that the demo worked. State what failed and what the evidence shows.

## 4. Recovery steps

| Symptom | Action |
|---|---|
| Job stuck queued | Start/restart the worker; check its terminal for errors |
| Search saved, but queueing could not be confirmed | Use **Retry starting search** on the same form. It reuses the saved search and enqueue key. **Open the saved search** shows what the API has stored. |
| Saved search has no jobs after navigating away | Open the dataset and check **Run searches on new videos** after checking the saved search status. This is the existing missing-video flow and is separate from the same-form retry. |
| Upload 422 | Try the known-good demo file; check `/api/v1/system/media` |
| Export not ready | Wait for the worker; check job status and `error_message` |
| Page blank | Rebuild frontend (`npm run build`) and refresh; check uvicorn is serving `/` |
| 401 | In a signed-in session, sign in again. For the local Alpha demo, verify the API started with auth OFF and the static token empty. |

## 5. Presenter allocation

Fill with real names only when the team supplies them:

| Segment | Presenter | Backup |
|---|---|---|
| Problem and scope | TBD | TBD |
| Requirements and design | TBD | TBD |
| Live demo | TBD | TBD |
| Evidence and plan | TBD | TBD |

## 6. Questions to expect

- *"Is that a real model?"* → Not in the mock demo (labelled). A real model, VideoJev-4B, is integrated as the `videojev` adapter and has only reference numbers on Charades-STA (the model was trained on it, so they do not show accuracy on new footage); held-out benchmark results (running since 2026-11-16) and validation on product footage are pending.
- *"Why 8 GB?"* → The dev laptop's GPU; VideoJev-4B runs on it with CPU offload (about 0.66× the video duration on ~30 s Charades-STA videos; reference set); 7B bf16 does not fit.
- *"What if the model is wrong?"* → A human labels every candidate; the proposal is preserved separately.
- *"Can two reviewers work at once?"* → Yes at the API level; the queue is single-worker today.
