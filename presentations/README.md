# Presentations

Versioned course decks. Each deck exists twice:

- **PPTX** (upload/presentation artifact) — `*.pptx`
- **Editable Markdown source** — `source/*.md`

Both are generated from one content model in `content/`, so they cannot drift apart.

## Decks

| File | Course use | Due / presented | Status |
|---|---|---|---|
| `01-project-vision-plan-v1.pptx` | Project Plan v1 + Intro/Vision/Plan | due 2026-11-02, presented 2026-11-03 | **LATE** (built 2026-11-05), **not uploaded** |
| `02-requirements-design-v1.pptx` | Requirements & Design | upload 2026-11-09 23:59, presented 2026-11-10 | ready; **upload/presentation evidence not recorded** |
| `03-status.pptx` | Status | upload **2026-11-16 23:59**, presented 2026-11-17 | **READY — 12 slides** |
| `sprint-01-review.pptx` | Sprint 1 review | after 2026-11-01 | produced late, not uploaded |
| `sprint-01-retrospective.pptx` | Sprint 1 retrospective | after 2026-11-01 | produced late, not uploaded |
| `sprint-02-review.pptx` | Sprint 2 review | after 2026-11-15 | **produced 2026-11-15** |
| `sprint-02-retrospective.pptx` | Sprint 2 retrospective | after 2026-11-15 | **produced 2026-11-15** |

## Rebuild

```powershell
# python-pptx is required (the DSH bundled Python already has it)
C:\Users\tonig\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe presentations\build_decks.py
```

or, with a project environment that has `python-pptx` installed from `presentations/requirements.txt`:

```powershell
.\.venv\Scripts\python.exe presentations\build_decks.py
```

Content lives in `content/*.py` as plain Python dicts (`layout`, `title`, `bullets`, `rows`, `notes`, …).
Supported layouts: `title`, `section`, `bullets`, `columns`, `table`, `kpi`, `quote`, `checklist`.
Speaker notes are written into the PPTX notes pane.

## Deck conventions (provisional)

The official `DSD Presentation Guidelines` have **not** been read — the FER materials page returns HTTP 401.
Until a team member downloads them:

- 16:9, title every slide, section kickers, footers with deck name and slide number;
- facts only: no invented metrics, attendance or feedback;
- mock/model limitations stated on the slide where they matter;
- separate review and retrospective decks (a superset of "one combined deck", so merging later is cheap);
- speaker notes carry the detail that should not be read aloud.

If the real guidelines require a different structure, re-check every deck and record the change in
`docs/course/OFFICIAL_GUIDELINES_CHECKLIST.md`.

## Upload checklist (manual — the harness cannot log in)

For each presentation, **before Monday 23:59**:

1. Open the deck in PowerPoint, check fonts render (`Segoe UI`) and the notes are present.
2. Export a PDF copy for safety (`File → Export`), keep it next to the PPTX.
3. Upload the **PPTX** (and PDF if requested) to the DSD course webpage.
4. Confirm the upload succeeded (visibility, version label, timestamp).
5. Record in `docs/course/DSD_DELIVERABLES_REGISTER.md`: uploader role, date/time, file name, evidence link.
6. Tell the supervisor the deck is available.

| Deadline | Deck | Owner (role) | Done? |
|---|---|---|---|
| 2026-11-02 23:59 (missed) | `01-project-vision-plan-v1.pptx` | Scrum Master | ☐ |
| 2026-11-09 23:59 | `02-requirements-design-v1.pptx` | Architect / Scrum Master | ☐ (evidence missing) |
| **2026-11-16 23:59** | `03-status.pptx` | Scrum Master | ☐ |
| 2026-11-30 23:59 | Alpha deck (Week 5) | Architect | ☐ |
| 2026-12-14 23:59 | Beta deck (Week 7) | Scrum Master | ☐ |
| 2027-01-11 23:59 | Final deck (Week 12) | All owners | ☐ |

> Uploading a file to Git is not an upload to the course page. Only a confirmed human upload counts.
