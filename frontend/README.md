# VLM Annotate — frontend

React + TypeScript single-page app for **VLM Annotate**, a university DSD
project. A reviewer creates a project, describes an action in natural language,
uploads a long single-view RGB video, runs asynchronous VLM candidate proposal,
marks each timestamped clip as **true positive — false positive — unreviewed**,
and exports the reviewed dataset as a ZIP.

No component library, no Tailwind, no router library: plain CSS in
`src/styles.css` and a hand-written hash router.

## Requirements

- Node.js 20.19+ or 22.12+ (Vite 7) — developed with Node 24
- npm 10+
- The FastAPI backend from `../backend` on `http://127.0.0.1:8000` for real data

## Install

```bash
cd frontend
npm install
```

`package-lock.json` is committed, so `npm ci` also works for a clean,
reproducible install.

## Development

Start the API first (from the repository root):

```bash
cd backend
../.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
```

Then, in another terminal:

```bash
cd frontend
npm run dev
```

Open <http://localhost:5173>. The interface uses relative `/api/v1/...` URLs.

### How the proxy works

`vite.config.ts` maps every request starting with `/api` to the backend:

```ts
server: {
  proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } }
}
```

This covers both the JSON API (`/api/v1/...`) and the FastAPI docs
(`/api/docs`), and avoids CORS during development. `vite preview` has the same
proxy under `preview.proxy`, because Vite does not inherit `server.proxy` in
preview mode.

In production FastAPI serves the built `dist/` folder at `/`, so the same
relative URLs work without any proxy.

### API token

If the deployment sets `VLM_API_TOKEN`, every `/api/v1` route except `/health`
requires `Authorization: Bearer <token>`. Use the **API token** field in the
header: the value is stored in `localStorage` under `vlm-annotate.api-token` and
attached to JSON, upload and export-download requests.

> Media caveat: browsers cannot attach an `Authorization` header to `<video
> src>` requests. A token-protected deployment will therefore reject
> `/videos/{id}/stream` and `/candidates/{id}/clip` with HTTP 401 unless the
> backend allows cookie/query auth on those routes. The open development server
> (`VLM_API_TOKEN` unset) works normally.

## Scripts

| Command           | What it does                                                   |
| ----------------- | -------------------------------------------------------------- |
| `npm run dev`     | Vite dev server on port 5173 with the `/api` proxy              |
| `npm run build`   | `tsc --noEmit` (strict type check), then `vite build` → `dist/` |
| `npm run preview` | Serve the built app on port 4173 with the same `/api` proxy     |
| `npm run test`    | `vitest run` — formatting and hash-routing unit tests           |

To exercise the full stack from the built files:

```bash
npm run build
# restart the backend afterwards: it mounts dist/ at startup
cd ../backend && ../.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
# open http://127.0.0.1:8000
```

## Screens and routes

| Route                              | Screen                                                    |
| ---------------------------------- | --------------------------------------------------------- |
| `#/`                               | Projects list, create/delete, per-project counts           |
| `#/projects/:id`                   | Workspace: stats, actions, videos, jobs, exports            |
| `#/projects/:id/review?job=:jobId` | Review: source player, clip player, labeling, filters       |
| anything else                      | Not-found screen                                           |

The review screen shows a prominent **MOCK CANDIDATES — no video pixels were
analysed** banner when the job's `adapter_name` is `mock`. No demo data is
seeded and no placeholder metrics are invented: every number comes from the API.

## Review workflow

- Selecting a candidate seeks the source `<video>` to `preview_start_seconds`.
- **Play clip** plays `/api/v1/candidates/{id}/clip` when `clip_status` is
  `ready`; otherwise the clip error is shown and the same window is played in
  the source player.
- Verdicts are saved with `PUT /api/v1/candidates/{id}/annotation`.
  Unreviewed is the absence of an annotation; **Reset to unreviewed** calls
  `DELETE`.
- Optional corrected start/end seconds are validated client-side
  (`0 <= start < end <= video duration`) and sent together with the annotation.
- Reviewer name and the auto-advance preference persist in `localStorage`.
- While a job is `queued` or `running`, the workspace and review screens poll
  every 2 seconds; the interval is cleared on unmount.

### Keyboard shortcuts (review screen)

| Key       | Action                                 |
| --------- | -------------------------------------- |
| `J`       | Save true positive                     |
| `F`       | Save false positive                    |
| `Space`   | Play/pause the clip (or source) player |
| `←` / `↑` | Previous visible candidate             |
| `→` / `↓` | Next visible candidate                 |

Shortcuts are disabled while typing in an input, textarea, select or
contenteditable element. `Space` is left to the browser when a button or link
has focus so it keeps activating that control.

## Project layout

```
frontend/
  index.html
  vite.config.ts          dev/preview proxy, build output, vitest config
  tsconfig.json           strict TypeScript, noEmit
  src/
    main.tsx              React root
    App.tsx               header (health, adapters, API token), routes, footer
    types.ts              TypeScript mirror of backend/app/schemas.py
    styles.css            mobile-first CSS, no framework
    lib/
      api.ts              typed fetch/XHR wrapper, ApiError, token handling
      format.ts           timestamps, durations, percent, bytes, dates
      format.test.ts      formatting unit tests
      router.ts           hash parsing and route matching
      router.test.ts      routing unit tests
      hooks.ts            useApiData (loading/error/reload) and stored prefs
    components/
      ui.tsx              chips, banners, stat tiles, progress, aria-live
      ActionsPanel.tsx    action definitions
      VideosPanel.tsx     XHR upload with <progress>, video table
      JobsPanel.tsx       start processing, job history, retry/cancel
      ExportsPanel.tsx    export creation and download
    pages/
      ProjectsPage.tsx
      ProjectPage.tsx
      ReviewPage.tsx
```

## Tests

```bash
npm run test
```

The suite covers `formatTimestamp` (mm:ss.mmm and hh:mm:ss.mmm), `formatDuration`
(hh:mm:ss), `percent`, byte sizes, date rendering, hash/query parsing and route
matching, including malformed URLs.

## Notes and limitations

- Timestamps are source-video-relative seconds with the backend's half-open
  `[start, end)` interval; the exact value is available in each timestamp's
  tooltip.
- Upload progress uses `XMLHttpRequest` because `fetch` cannot report upload
  progress.
- Export downloads are fetched (so the bearer token can be sent) and saved
  through a temporary object URL; very large archives are buffered in browser
  memory.
- The UI targets 375 px and 1440 px widths, uses CSS grid/flex, visible focus
  styles, labelled controls and `aria-live` announcements for job progress,
  save results and errors.
