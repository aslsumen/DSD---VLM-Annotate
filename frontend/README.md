# VLM Annotate — frontend

React + TypeScript single-page app for **VLM Annotate**, a university DSD
project. It follows the Requirements Definition v1.2 and Design Description v1.2
(`docs/inputs/2026-11-12/`) and the "Industry" visual system of the Claude
mockup: Barlow Condensed headings over Barlow, a steel-blue accent and square
hairline frames with registration corners, in light and dark themes.

The loop is **dataset → prompt → detection → review → JSON export**, with
sign-in, global roles and invitations.

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

Start the API and a worker first (from the repository root):

```bash
cd backend
../.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000   # terminal 1
../.venv/Scripts/python.exe -m app.worker --loop                  # terminal 2
```

Then, in another terminal:

```bash
cd frontend
npm run dev
```

Open <http://localhost:5173>. The interface uses relative `/api/v1/...` URLs.

### How the proxy works

`vite.config.ts` maps every request starting with `/api` to the backend
(`server.proxy` and `preview.proxy`), which covers the JSON API and `/api/docs`
and avoids CORS during development. In production FastAPI serves the built
`dist/` folder at `/`, so the same relative URLs work without any proxy.

The fonts are loaded from Google Fonts (`index.html`); without network access the
app falls back to the system sans-serif.

## Accounts and sign-in

At start-up the app verifies the session or anonymously checks access to `GET /api/v1/datasets`:

| Mode | When | What the user sees |
| --- | --- | --- |
| Checking access | An access check or retry is in progress | Loading status while the workspace stays closed |
| Signed in | A session token is stored and `GET /auth/me` accepts it | Sidebar with the user's name and global role; pages filtered by role |
| Development | The anonymous dataset request returns HTTP 200 with a valid dataset list | Development mode, with the demo controls and a **Sign in** link |
| Signed out | The backend returns 401 for anonymous access, or an active session ends | Sign-in and public account pages |
| Authentication unavailable | The access check is forbidden (403), fails to reach the server, or returns a server error or unexpected response | An access error with **Try again**. Dataset pages stay gated |

- **Sign in** (`POST /auth/login`) stores the session token in `localStorage`
  (`vlm-annotate.api-token`) and sends it as `Authorization: Bearer <token>`.
  Wrong credentials always show the same message (NFR-14).
- **Session checks.** The browser checks `/auth/me` 30 seconds after the previous check settles.
  Checks time out after 10 seconds of active browser time. A verified role change updates the route
  guards. A current authenticated 401 ends the session and stops protected requests and polling.
  A 403, timeout, server or transport error from the session check closes the workspace and keeps
  the token for retry. The app retries a stored session at the next check or when **Try again** is
  selected. A resource-level 403 denies that request and leaves the session in place.
- **Review after reauthentication.** Protected URLs stay in the address bar. Unsaved time and note
  edits remain in memory and can be recovered on the same page by the same user. Changing accounts,
  explicitly signing out in that tab or reloading the document clears those drafts.
- **Sign out** is available in the workspace sidebar. It closes the workspace locally, aborts pending
  client work and attempts revocation with the outgoing bearer token. A failed logout reports that
  server revocation could not be confirmed. A confirmed logout in the initiating tab returns to
  Development mode only after a successful anonymous check.
- **Tabs.** A tab closes its workspace when the shared token is removed. A new token opens a
  workspace after successful verification. Other tabs show sign-in after a shared sign-out,
  including in development. Refreshing without a stored token repeats the anonymous access check.
- **Invitations** (Users page): no mail transport exists yet, so the invitation
  link is shown once to the inviter. `#/invite/:token` creates the account
  (full name + password, at least 8 characters); used or expired links show an
  explicit message (NFR-11, 48 h).
- **First administrator**: created with `POST /auth/bootstrap` and
  `VLM_BOOTSTRAP_TOKEN` (see the installation manual); there is no UI for it.
- **Roles**: Administrators and Dataset Administrators see Export and Users,
  create datasets, upload and launch searches. Annotators only review.

## How v1.2 concepts map to the current API

The backend does not have the v1.2 Dataset/Search model for videos yet. The
interface uses what exists today:

| v1.2 concept | Current API |
| --- | --- |
| Dataset (name only, DS-2) | Project (`/projects`) — it holds videos, prompts, jobs, candidates, exports |
| Search (one prompt on every video, PR-1) | One action (`/projects/{id}/actions`) plus one job per video (`POST /projects/{id}/actions/{action_id}/jobs`) |
| Search status (queued, running, done, partial, failed — DET-3) | Aggregated in the client from the latest job of each video (`src/lib/search.ts`) |
| Adding videos to a dataset with searches (DS-7) | After upload, a confirmation dialog re-runs every existing search on the new videos only |
| Accept / reject (REV-3) | `PUT /candidates/{id}/annotation` with `true_positive` / `false_positive` |
| Decisions are final (REV-3) | Decided candidates are read-only in the UI (the API still allows changes) |
| One reviewer per video (REV-5) | Derived in the client from the first saved decision on the video (no backend lock yet) |
| JSON export (EXP-1, EXP-2) | Built in the browser from the reviewed candidates (Design 4.3 proposal format); the worker's ZIP package stays available |

The backend `/datasets` entity (Sprint 3) is not used by these screens yet,
because videos still belong to projects.

## Screens and routes

| Route | Screen | Roles |
| --- | --- | --- |
| `#/signin`, `#/forgot-password`, `#/invite/:token` | Sign in, password reset info, invitation acceptance | Public |
| `#/` | Datasets: cards with videos, searches and review progress; New dataset | All |
| `#/datasets/:id` | Dataset: MP4 drop zone with progress, video table, searches with status, restart; delete a video, a search or the dataset; **Run searches on new videos** (every search on the ready videos it has not processed, DS-7) | All (managers can edit) |
| `#/datasets/:id/searches/new` | New search: prompt, customer examples, optional short name (PR-3), model | Managers |
| `#/datasets/:id/searches/:searchId` | Search status: steps, progress, per-video jobs with retry / cancel | All |
| `#/datasets/:id/searches/:searchId/review` | Review screen | All |
| `#/export?dataset=:id` | Export: dataset, search, include rejected, statistics, JSON download, ZIP package | Managers |
| `#/users` | Users: list (administrators), invitations | Managers |

Old links (`#/projects/:id`, `#/projects/:id/review?job=…`) open the dataset page.

## Review screen

- One list with the candidates of every video of the search, filtered by status
  (All, Unreviewed, Accepted, Rejected) with counts, the number of videos, and a
  sort by confidence or time. There is no filter by video (NFR-7).
- The **full video** plays from the selected candidate's start; the reviewer can
  move before and after it (REV-1). A **Clip** view plays the extracted clip.
- A full-video strip shows every candidate of that video; a zoomed track with
  draggable start/end handles, ±0.5 s steppers and numeric fields adjusts the
  bounds (REV-2). The model times stay stored (NFR-5).
- **Accept / Reject** are equal-size buttons; the decision is final.
- A **Mock candidates** banner is shown when the search used the `mock` model.

| Key | Action |
| --- | --- |
| `A` (or `J`) | Accept |
| `R` (or `F`) | Reject |
| `N` | Next unreviewed |
| `↓` / `↑` | Next / previous candidate |
| `Space` | Play / pause |
| `?` | Shortcuts |

Shortcuts are disabled while typing in a field.

## Scripts

| Command | What it does |
| --- | --- |
| `npm run dev` | Vite dev server on port 5173 with the `/api` proxy |
| `npm run build` | `tsc --noEmit` (strict type check), then `vite build` → `dist/` |
| `npm run preview` | Serve the built app on port 4173 with the same `/api` proxy |
| `npm run test` | `vitest run` — formatting, routing and search/review logic |

## Project layout

```
frontend/src/
  main.tsx                React root
  App.tsx                 session provider, route table, role guards
  types.ts                TypeScript mirror of backend/app/schemas.py
  styles.css              design tokens, components, light/dark, responsive
  lib/
    api.ts                typed fetch/XHR client, ApiError, session token
    session.tsx           sign-in state (signed in / development / signed out)
    search.ts             search status, review counts, titles, JSON export
    router.ts             hash routes
    format.ts, hooks.ts   formatting, data loading and stored preferences
  components/
    ui.tsx                icons, frames, chips, notices, dialog, toast
    Shell.tsx             sidebar layout, theme toggle, sign out
  pages/
    AuthPages.tsx  DatasetsPage.tsx  DatasetPage.tsx  NewSearchPage.tsx
    SearchPage.tsx  ReviewPage.tsx  ExportPage.tsx  UsersPage.tsx
```

## Limitations (waiting for the backend)

- Password reset (USR-6), role changes and deactivation (USR-7), dataset
  assignment (USR-3) and invitation emails (USR-5) have no API yet.
- The API lets Dataset Administrators invite Annotators only (v1.2 also allows
  Dataset Administrators).
- REV-3 and REV-5 are enforced in the client only.
- The JSON export follows the Design 4.3 proposal; the OpenLABEL-based schema is
  still to be agreed.
- With sign-in required, the legacy project/video/job routes do not check roles
  or enforce Dataset membership. Review writes still use the legacy annotation routes.
  `<video>` requests cannot send the bearer header (protected media, R-18).
- Session tokens use the existing browser storage and have an absolute server expiry. The backend
  has no inactivity-based expiry, token refresh or password-reset endpoint. The forgot-password
  screen remains informational. Closing a browser request cannot undo writes already accepted by
  the API.
