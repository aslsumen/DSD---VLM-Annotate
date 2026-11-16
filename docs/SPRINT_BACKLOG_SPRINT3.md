# Sprint Backlog — Sprint 3 (2026-11-16 → 2026-11-29)

**Type:** living artifact · **Owner:** Scrum Master (role placeholder) · **Created:** 2026-11-15 (draft)
**Sprint goal:** *By 2026-11-29, a user can sign in with a global role, see only assigned datasets, run one
prompt over all videos of a dataset, review candidates across videos, and export OpenLABEL-based JSON — with a
real detector (self-hosted VideoJev-4B; Gemini as an optional verify stage) measured on a public test set.*

**Capacity:** still **UNKNOWN** (no declared availability). Estimates are provisional story points, not hours.
Target 80–85 % of declared capacity once the table is filled.

> **Status note 2026-11-16 (detector work):** the plan above is unchanged. The real detector is VideoJev-4B
> through the `videojev` adapter ([ADR-0007](decisions/ADR-0007-videojev-zero-shot-grounding-adapter.md)), not
> Gemini; Gemini exists only as an optional engine verify stage, off in the adapter. S3-11 is superseded,
> S3-12 is done (Charades-STA only), S3-13 is partly done (engine `eval` CLI). Charades-STA is reference only (VideoJev
> was trained on it); the SPEC target check moves to the held-out composite benchmarks (S3-17, running since
> 2026-11-16, results pending; `video_grounding/docs/EVALUATION.md`). The real-model smoke on the RTX 3070 laptop is pending.

## 1. Committed scope (Must)

| ID | Task | Refs | Est. | Owner (role) | Notes |
|---|---|---|---|---|---|
| S3-01 | Auth data model + migration: users, invitations, sessions, dataset_assignments | USR-1…5, NFR-11 | 8 | Backend | Global roles, email-only |
| S3-02 | Auth API: login/logout/refresh, password hashing, session revocation, lockout | NFR-12…14 | 8 | Backend | 2 h inactivity, 5/15 min |
| S3-03 | Invitation flow + email abstraction (SMTP/provider) | USR-5 | 5 | Backend | Single-use 48 h; Admin + Dataset Admin |
| S3-04 | RBAC middleware + dataset scoping on every route | USR-2/3/4 | 5 | Backend | Deny by default |
| S3-05 | Dataset entity + API + assignments (migrate Project) | DS-1/2/3 | 8 | Backend | Data migration for existing rows |
| S3-06 | Search entity: one prompt over all videos, fan-out jobs, status aggregation | PR-1, DET-3 | 8 | Backend | Partial per-video results |
| S3-07 | UI: login, invitation acceptance, user management | USR-1…7 | 5 | Frontend | Route guards |
| S3-08 | UI: datasets list/detail, upload, search launch, search history | DS-1…3, PR-1 | 8 | Frontend | Reuse upload component |
| S3-09 | Cross-video review list, accepted/rejected vocabulary, review flags | REV-1…4 | 5 | Frontend | Pagination |
| S3-10 | OpenLABEL-based JSON export (multi-interval) + async job | EXP-1 | 8 | Backend | Schema confirmed with customer |
| S3-11 | Gemini adapter: `GroundingBackend`, quota guard, retry, JSON validation | DET-1, NFR-6 | 8 | ML | **Superseded 2026-11-16** by the `videojev` adapter (ADR-0007). Gemini is only the engine's optional verify stage (off in the adapter); privacy approval R-20 matters only if verify is on |
| S3-12 | Test-data ingestion (Charades-STA subset) + licence check | NFR-5 | 5 | ML | Done 2026-11-16 (Charades-STA only). Non-commercial caveat |
| S3-13 | KPI harness: recall, R@IoU, complete clip, boundary adjustment | NFR-5 | 5 | ML | First measurements done 2026-11-16 (engine `eval` CLI; Charades-STA reference only, composites in S3-17); reviewer boundary-adjustment KPI not built |
| S3-14 | Alpha deck + evidence + upload checklist | D-19 | 5 | Scrum Master | Upload 2026-11-30 |
| S3-15 | Carry-over: validate a real 10–30 min video | NFR-4 | 3 | QA | From Sprint 2 |
| S3-16 | Integration tests: auth, permissions, dataset scoping | NFR-11…14 | 5 | QA | Security-critical |
| S3-17 | Run held-out composite benchmarks, re-check `min_event_score` (0.5 is provisional), report KPIs | NFR-5 | 5 | ML | Started 2026-11-16 on the RTX 3070 laptop (PB-70); results pending |

**Total committed:** ~99 SP. **This is likely more than the team can absorb in two weeks without capacity
data** (R-22). Triage proposal: S3-01…S3-07 and S3-14 are the minimum; S3-08…S3-13 can slip into Sprint 4 if
the detector or JSON schema is blocked.

## 2. Daily plan (working days only)

| Date | Focus | Gate |
|---|---|---|
| Mon 16 Nov | Upload Status deck (23:59); auth data model; confirm capacity | deck evidence |
| Tue 17 Nov | Status presentation; auth API; JSON schema proposal to customer | feedback recorded |
| Wed 18 Nov | RBAC middleware; dataset entity migration | two roles enforced |
| Thu 19 Nov | Search entity + fan-out; UI login | sign-in works end-to-end |
| Fri 20 Nov | Invitations; dataset UI; real-video validation | invite → sign-in works |
| Mon 23 Nov | JSON export v1; real-model smoke on the 8 GB laptop (replaces the Gemini adapter spike) | first JSON export |
| Tue 24 Nov | Cross-video review; review flags | one list across videos |
| Wed 25 Nov | KPI harness; composite benchmark results (S3-17); product-footage run | KPI numbers on product footage |
| Thu 26 Nov | Integration tests; fix defects | tests green |
| Fri 27 Nov | Alpha deck draft; limitations documented | deck source ready |
| Sat 28 Nov | **No work assumed** | — |
| Sun 29 Nov | Sprint 3 gate: Alpha prototype testable | PASS/FAIL evidence |

## 3. Exit criteria (Alpha gate, 2026-11-29)

- [ ] Sign-in with global roles; users see only assigned datasets
- [ ] Invitation flow works (single-use, 48 h)
- [ ] Search over all videos of a dataset returns candidates
- [ ] Review across videos with accept/reject and final timestamps
- [ ] JSON export with intervals and provenance
- [ ] Real detector measured on a public test set (or documented blocker) — VideoJev-4B on held-out composites (S3-17, running since 2026-11-16, pending; Charades-STA is reference only)
- [ ] Alpha deck ready for upload by 2026-11-30 23:59
- [ ] Limitations explicit; no fabricated metrics

## 4. Dependencies and blockers

| Dependency | Owner | Needed by |
|---|---|---|
| Client answers: privacy, reviewer, dataset meaning, JSON fields | Product Owner | 2026-11-17 |
| Privacy approval for Gemini (only if verify is turned on; not needed for the self-hosted detector) | Backend owner | 2026-11-18 |
| Compute decision (12 GB laptop / GPU / API); VideoJev-4B already runs on an 8 GB laptop with offload, slowly | Architect + supervisors | 2026-11-19 |
| Team capacity and roles | Scrum Master | 2026-11-16 |
| Official guidelines files (401 wall) | Team member with AAI | 2026-11-16 |
| Customer's OpenLABEL example | Product Owner | 2026-11-18 |

## 5. Notes

- Mock stays the CI default even with the `videojev` adapter integrated: tests must run without network or GPU.
- Every delivered PDF must be generated from repository Markdown (Sprint 2 retro action A-6).
- Do not start optional features (summaries, semantic search, multi-model UI) before the Alpha gate.
