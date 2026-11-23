# User Manual

**Applies to:** Sprint 2 vertical slice (2026-11-05) · **UI:** desktop and mobile browser

> **Current limitation — read before demoing.** By default, candidate intervals are produced by the **mock
> adapter**: a deterministic generator that does *not* look at the video pixels. The UI shows a MOCK banner on
> such jobs and the exported manifest marks them. A real detector, the `videojev` adapter (VideoJev-4B), is
> available on a worker configured with a GPU ([INSTALLATION_MANUAL.md](INSTALLATION_MANUAL.md) §5.1). It is
> integrated, but not yet validated on product footage. Search time is measured for one video and one prompt
> per job; see the [single-prompt speed results](../video_grounding/docs/EVALUATION.md#speed-kpis) for actual
> times and model/cache conditions. With it, review every candidate: on held-out long videos it found 86% of the true cooking events and 47% of the true driving events, and on driving it gives almost as many candidates for actions that are not in the video as for ones that are (`video_grounding/docs/EVALUATION.md`).

## 1. What you can do

1. Organise work into **projects**.
2. Describe the action you are looking for in **natural language**.
3. Upload a long single-view RGB **video**.
4. Start **asynchronous** processing and watch its progress.
5. **Review** timestamped candidates and label them true/false positive.
6. **Export** a dataset ZIP with labels, clips and provenance.

## 2. Sign in / access

If the deployment sets `VLM_API_TOKEN`, the UI asks for an API token once and remembers it in the browser's
local storage. Without a token, the API returns `401 UNAUTHENTICATED`.

> **Known limitation:** a browser cannot attach the token to `<video>` playback requests, so a
> token-protected deployment cannot show source videos or clips (they return 401). Use a deployment without
> `VLM_API_TOKEN` until media authentication is implemented.

## 3. Create a project

1. Open the app (`http://127.0.0.1:8000` or the Vite dev URL).
2. On **Projects**, choose a name (e.g. *Street interviews*) and an optional description.
3. Select **Create project**. The card shows counts of videos, candidates, reviewed items and exports.

Deleting a project removes its videos, clips, jobs, labels and exports. The confirmation dialog is deliberate:
there is no undo.

## 4. Define the action

Inside a project, in **Action definitions**:

- **Name**: a short handle (`person waves`).
- **Description**: the sentence the model will receive. Be concrete about appearance, motion and viewpoint:
  *"a person raises their right hand and waves at the camera, upper body visible"*.
  Vague text produces vague candidates. At least 3 characters are required.
- Names must be unique within a project; the API returns `409 ACTION_NAME_ATTACHED`… (see
  [API_CONTRACTS.md](API_CONTRACTS.md)) if duplicated.

## 5. Upload a video

1. Choose an action-agnostic video file: `.mp4 .mov .m4v .webm .mkv`.
2. Limits: up to **2 GiB** and **4 hours**; the product target is **10–30 minutes**.
3. Upload streams to the server with a progress bar. The server verifies the container signature, probes the
   duration and only then marks the video **ready**.
4. Rejections are explicit: `UNSUPPORTED_VIDEO_EXTENSION`, `UNRECOGNISED_CONTAINER`, `UPLOAD_TOO_LARGE`,
   `VIDEO_DURATION_OUT_OF_RANGE`, `MEDIA_PROBE_FAILED`.

The original filename is kept as metadata; the stored file gets a generated name.

## 6. Start processing

1. In **Processing**, choose a ready video and an action.
2. Select **Start processing**. The request returns immediately; the job appears as **queued**.
3. A separate worker process picks it up: **running** with a progress bar, then **succeeded** or **failed**
   with an error code.
4. **Retry** is available for failed jobs. **Cancel** is available while a job is queued.
5. The list refreshes automatically every two seconds while something is queued or running.

If no worker is running, jobs stay queued — this is the most common setup mistake.

## 7. Review candidates

Open **Review** for a succeeded job.

| Control | Effect |
|---|---|
| Candidate row | Seeks the source video to the preview start and loads the clip |
| **True positive (J)** | Saves `true_positive` for this candidate |
| **False positive (F)** | Saves `false_positive` |
| **Reset to unreviewed** | Deletes the label; the candidate returns to the unreviewed pool |
| **Play clip** | Plays the generated preview clip; disabled with an explanation if extraction failed |
| ← / → | Previous / next candidate |
| Space | Play/pause the active player |
| Filters | All · Unreviewed · True positives · False positives |
| Correction fields | Optional new start/end in seconds; validated (`0 ≤ start < end ≤ duration`) |
| Auto-advance | Moves to the next unreviewed candidate after a label |
| Reviewer / note | Stored with the label; reviewer is remembered in the browser |

The counter shows how many candidates remain unreviewed. **An unreviewed candidate is not a negative**; it is
simply not part of a verified dataset yet.

If the job used the mock adapter, a banner states that no pixels were analysed. Jobs from the `videojev` adapter have no such banner; their candidates may be zero for a video (the action does not occur) or many (all events are kept, best score first).

## 8. Export a dataset

1. In **Exports**, choose whether to include unreviewed candidates (default **no**).
2. The export runs asynchronously; when it is **ready**, select **Download**.
3. The ZIP contains `manifest.json`, `labels.csv`, `README.txt` and `clips/`.
   Format details: [DATASET_FORMAT.md](DATASET_FORMAT.md).

The server refuses to export when nothing has been reviewed (`NO_REVIEWED_CANDIDATES`) unless you explicitly
include unreviewed items.

## 9. Keyboard and accessibility

- All controls are focusable and labelled; status changes are announced through an `aria-live` region.
- Shortcuts are disabled while typing in an input or textarea.
- The layout works at 375 px (single column) and 1440 px (two columns).

## 10. Known limitations (Sprint 2)

| Limitation | Effect | Planned |
|---|---|---|
| Mock candidate generation (default adapter) | Intervals are plausible but arbitrary | Use the `videojev` adapter on a GPU worker; real-model smoke and product-footage validation pending |
| Real detector quality | Held-out long videos (2026-11-22): recall 0.86 cooking and 0.47 driving vs the 0.85 target; on driving, turns are found but lane moves, overtakes and most stops are missed; a prompt for something not in the video still returns about 3.5 candidates per cooking video and 8.4 per driving video | Human review of every candidate; validation on product footage |
| Single worker | One long job delays others | Parallel workers with PostgreSQL (later) |
| No multi-user accounts | One shared optional token | Deferred (OPT-06) |
| No bulk review | One label at a time | Deferred (OPT-05) |
| Cancel only while queued | A running ffmpeg/model call finishes | Documented trade-off |
| English UI | — | Acceptable for the course |

## 11. Getting help

- API reference: `http://127.0.0.1:8000/api/docs`
- Setup problems: [INSTALLATION_MANUAL.md](INSTALLATION_MANUAL.md) §8
- Data questions: [DATASET_FORMAT.md](DATASET_FORMAT.md)
