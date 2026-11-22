# Week 04 Report — 2026-11-16 → 2026-11-22 (draft, written 2026-11-19)

**Sprint:** 3 (2026-11-16 → 2026-11-29) · **Status:** in progress (Thursday)
**Team capacity:** still not supplied by the team

> Draft mid-week report. Upload/presentation evidence and client answers are only recorded when they exist in
> this repository; nothing is assumed.

## 1. Goal

Deliver the Status presentation, publish the Sprint 2 review/retrospective, and start Sprint 3 with accounts,
global roles, datasets and the export schema.

## 2. Done this week

| Item | Status | Evidence |
|---|---|---|
| Repository onboarding fixed (clone → run) | **Done** | `scripts/setup.ps1`, `scripts/setup.sh`; clean-clone verification |
| Status deck ready (12 slides) | **Done 2026-11-15** | `presentations/03-status.pptx` |
| Sprint 2 review/retrospective decks | **Done 2026-11-15** | `presentations/sprint-02-*.pptx` |
| OpenLABEL export schema draft | **PR #47 open** (docs + example + validation) | `docs/export/` |
| Auth data model + migration | **In review** | `feat/auth-datasets`, migration `d03f1c4ffd30` |
| Login/logout/session/lockout API | **In review** | `app/api/auth.py`, `test_auth.py` |
| Invitations (single-use, 48 h) | **In review** | `app/api/auth.py`, `test_auth.py` |
| Global roles + dataset scoping | **In review** | `app/deps.py`, `app/api/datasets.py` |
| Dataset CRUD + memberships | **In review** | `app/api/datasets.py`, `test_datasets.py` |

**Verification:** 90 backend tests passing (10 new); ruff clean; migration verified on a fresh database with
`alembic check` and a bootstrap → login → dataset call against the migrated schema.

## 3. Not done / unverified

| Item | Status | Why |
|---|---|---|
| Status presentation (2026-11-17) | **UNVERIFIED** | No presentation notes or upload evidence recorded |
| Login/invitation UI | Not started | Frontend pair scheduled after the API contract |
| Refresh tokens, password reset | Not started | Should-priority, after the Alpha gate |
| Project/video/job routes on sessions | Not started | Needs signed media URLs first (R-18) |
| Video-to-dataset migration | Not started | Dataset entity exists; videos still belong to projects |
| Real 10–30 min video validation | Not run | Carried from Sprint 2 |
| Capacity table, supervisor access, guidelines | Open | Human actions |

## 4. Next (Fri 20 – Sun 22)

1. Merge/review `feat/auth-datasets` and PR #47.
2. Frontend: login, invitation acceptance, dataset list/detail.
3. Decide the Project → Dataset migration (videos, jobs, exports).
4. Run one real 10–30 minute video and save the evidence.
5. Update the Sprint 3 burndown and the Alpha deck outline (upload 2026-11-30 23:59).

## 5. Dependencies

- Client answers on privacy, reviewer attribution, dataset meaning and JSON fields.
- Gemini key status and privacy approval.
- Team capacity and supervisor access.
