# Sprint 2 Retrospective

*What worked, what caused rework, and five actions for Sprint 3*

Static report slides · Sprint 2: 2026-11-02 → 2026-11-15
Produced 2026-11-15 from repository evidence; no retrospective meeting is recorded
Team sentiment was not measured and is not invented

---

## 1. How this retrospective was written

*Method*

- Inspected the repository, test results, evidence files and deliverable register
- Separated verifiable facts from assumptions about people
- No meeting minutes exist; no attendance or feedback is claimed
- Team members must replace assumptions with real observations

## 2. Went well / did not go well

*Facts*

**Went well**

- A full vertical slice works and is tested
- Evidence is reproducible (tests, smoke JSON)
- Mock is labelled, never presented as AI
- Customer answers analysed quickly into a brief
- Scope discipline: optional features frozen
- Docs aligned to the team's v1.1 documents

**Did not go well**

- No repository existed before 5 Nov
- Upload/submission evidence not recorded
- Requirements/design rewritten twice (v1.0→v1.2)
- No capacity or team names all sprint
- Living artifacts not accessible to supervisors
- No real detector, long video or KPI measured

## 3. Root causes behind the misses

*Causes*

| Cause | Evidence | Fix |
|---|---|---|
| No single source of truth for documents | Team PDFs vs repo v1.0 vs v1.2 | Repo is source; PDFs generated from it |
| No evidence protocol per deadline | No upload record for 10/13 Nov | Owner + evidence cell before work |
| External inputs arrived late | Guidelines 401; client answers 9 Nov | Risk + human action with date |
| No capacity data | Empty team table | Fill capacity before Sprint 3 planning |
| Tooling fragility (encoding) | PowerShell corrupted accents | Verify encoding after scripted edits |

## 4. Five actions with owners and dates

*Actions*

| # | Action | By | Signal |
|---|---|---|---|
| A-1 | Upload Status deck; record evidence | 16 Nov | link in register |
| A-2 | Record 10/13 Nov submission evidence | 17 Nov | register updated |
| A-3 | Write client answers into repo | 17 Nov | CUSTOMER_DECISIONS updated |
| A-4 | Fill capacity and supervisor access | 18 Nov | table complete; link works |
| A-5 | Validate a real 10–30 min video | 20 Nov | smoke evidence with real file |

## 5. Sprint 3 experiment

*Experiment*

> One source of truth: every document lives in the repository, and every submitted PDF is generated from it and recorded with owner, date and evidence.

## 6. What the sprint taught us

*Learning*

- A working prototype is not an MVP when the customer adds roles and access
- Documenting honestly costs less than explaining fabricated progress
- External approvals (privacy, guidelines) are schedule risks, not paperwork
- Mock-first was right: it exposed design flaws before the model arrived
- Re-baselining the gate with the supervisor is a decision, not a failure

## 7. What this retrospective does not know

*Honesty*

- Who attended the 10 Nov presentation and what feedback was given
- What was submitted on 13 Nov, and how
- What the customer answered on 13 Nov
- How the team felt about the sprint
- Only the team can fill these gaps; guessing would poison Sprint 3
