# Sprint 2 Retrospective — observed facts and actions

**Sprint:** 2 (2026-11-02 → 2026-11-15) · **Written:** 2026-11-15
**Type:** static presentation source → `presentations/sprint-02-retrospective.pptx`

> **No retrospective meeting is recorded.** This is an evidence-based retrospective written by the
> implementation harness from repository facts. Team members must replace assumptions with real observations.

## 1. What went well (verifiable)

| Observation | Evidence |
|---|---|
| A complete vertical slice works and is tested | 56 backend + 21 UI tests; smoke 26/26 |
| Evidence is reproducible, not verbal | `docs/evidence/*.json`, test commands in `TEST_PLAN.md` |
| Mock was always labelled, never presented as AI | MOCK banner, `provenance.mock`, deck wording |
| Customer answers were analysed quickly into actionable docs | `CUSTOMER_DECISIONS.md`, `CLIENT_MEETING_BRIEF_2026-11-13.md` |
| Scope discipline held: optional features stayed frozen | Backlog E9 untouched |
| Repository docs were aligned to the team's v1.1 documents | `REQUIREMENTS.md` v1.2, `DESIGN_DESCRIPTION.md` v1.2 |

## 2. What did not go well

| Problem | Evidence | Impact |
|---|---|---|
| No repository before 5 Nov | folder had only prompts + calendar | Sprint 1 delayed into Sprint 2 |
| Submission evidence missing | no upload record for 10/13 Nov | course compliance unverifiable |
| Requirements/design reworked twice | v1.0 → v1.2 in one week | wasted effort, inconsistency risk |
| No capacity/names | empty table | no credible plan or burndown |
| Living artifacts inaccessible | local files only | continuous course requirement unmet |
| No real detector/video/KPI | mock only; synthetic 2 min | core value unproven |
| Tooling incident | PowerShell double-encoded accents in six docs | detected and repaired, but cost time |

## 3. Root causes

1. **No single source of truth for documents.** Team PDFs, repository Markdown and the prompt pack described
   different versions; aligning them forced a rewrite.
2. **No evidence protocol per deadline.** Nothing forced a record of who uploaded/submitted what and when.
3. **External inputs arrived late or blocked.** Guidelines behind a login wall; customer answers on 9 Nov;
   OpenLABEL example never received.
4. **No capacity or ownership data.** Tasks could not be balanced or escalated.
5. **No encoding check after scripted edits.** A PowerShell round-trip corrupted non-ASCII text.

## 4. Actions (owner TBD until names are supplied)

| # | Action | Owner | By | Success signal |
|---|---|---|---|---|
| A-1 | Upload the Status deck and record evidence | Scrum Master | 2026-11-16 | link in register |
| A-2 | Record 10 Nov presentation and 13 Nov submission evidence | Scrum Master | 2026-11-17 | register updated |
| A-3 | Write the 13 Nov client answers into `CUSTOMER_DECISIONS.md` | Product Owner | 2026-11-17 | decisions updated |
| A-4 | Fill capacity, roles and supervisor access | Product Owner | 2026-11-18 | table complete; access link works |
| A-5 | Validate a real 10–30 min video and record smoke evidence | QA | 2026-11-20 | evidence JSON with real file |
| A-6 | Make the repository the single source; generate PDFs from it | Architect | Sprint 3 planning | one source, versioned |

## 5. Experiment for Sprint 3

**"One source of truth, with evidence attached to every deliverable."** Every document lives in the repository,
every submitted PDF is generated from it, and each deliverable has an owner, a date and an evidence cell.
Checked at Sprint 3 planning and at the 29 Nov gate.

## 6. Team sentiment

**Not measured.** A real retrospective should collect it; inventing a mood score would be dishonest.
