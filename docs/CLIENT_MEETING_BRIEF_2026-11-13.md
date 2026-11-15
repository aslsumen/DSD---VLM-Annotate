# Client Meeting Brief — 13 November 2026

**Prepared:** 2026-11-12 · **For:** client meeting with Gordan Kreković (Visage Technologies)
**Prepared by:** implementation harness on behalf of the team · **Status:** internal working document

**Inputs analysed:** Requirements Definition v1.1 (`docs/inputs/2026-11-12/`), Design Description v1.1
(same folder), Datasets memo (`Datasets.pdf`), customer emails of 2026-10-30 (kick-off), 2026-11-05 and the
latest reply (CE-2), supervisor emails of 2026-11-04/05/09, and the current repository.

---

## 1. Executive summary

1. **The customer answered the open requirements questions** in the latest email: Dataset Administrators can
   create datasets, upload, export **and invite users**; **roles are global**; accounts are **email-only**
   (no username); and the workflow is confirmed as upload-many-then-search-then-review, **not** a continuous
   chain.
2. **The export is JSON based on the customer's OpenLABEL example**, and one action may have **several
   separate time intervals**. Video summaries and keyword tags are automatic but **outside the MVP**.
3. **The customer provided a Gemini API key** (free tier) — a cloud VLM is now a viable path. This raises the
   one blocking legal/technical question: **may videos that show faces be sent to an external API?**
4. **The current repository is a working vertical slice** (upload → async job → candidates → review → ZIP
   export, with a mock model) but it predates this scope: it has **no accounts, roles, dataset model, search
   entity or JSON export**. Reusable: media pipeline, job queue, review UX, clip generation, provenance.
5. **The two course documents are due tomorrow, 2026-11-13 23:59** (Requirements Definition v1 and Design
   Description v1). The repo documents have been updated to **v1.2** to include CE-2; the team must regenerate
   the submitted PDFs from them or reconcile with the existing v1.1 PDFs.

## 2. What changed since Requirements v1.1

| # | Area | v1.1 said | Latest customer answer (CE-2) | Documents updated |
|---|---|---|---|---|
| 1 | Dataset Administrator permissions | Create/upload/export assumed; invite = No* | Create, upload and export **confirmed**; **may also invite users by email** | Requirements §3.2, USR-4, USR-5 |
| 2 | Role scope | Open question (global vs per dataset) | **Global roles**; Dataset Admin can do everything an Annotator can **on their own dataset**; to annotate elsewhere, use a separate global Annotator account | Requirements §3.1, USR-2/3/4 |
| 3 | Account creation | Email **or username**, to confirm | **Email-only invitation**: email + full name + password + optional organization; admin assigns role and datasets | USR-1, USR-5 |
| 4 | Workflow | "Upload → prompt → review → export" | Same, **but not continuously**: upload several videos, later run one or more prompts, annotators review later | US-1…US-5, NFR-3 |
| 5 | Gemini / external API | Open decision; no key | **Gemini API key supplied** (free tier; ~3,600 images/request, 1M TPM, 1,500 req/day; budget possible) | Design §6.1, open decisions |
| 6 | Compute | Asked for Nov 4, unanswered | Supervisors: **12 GB VRAM laptops available now**; remote access TBD; AWS possible but slow; Colab suggested | Design §7 |
| 7 | Test datasets | Open | Team memo: Charades-STA best first fit; TimeLens-Bench for KPIs; MEVA/DMD for customer domains; licence caveats | `docs/MODEL_EVALUATION.md` |

**Not answered by the customer:** whether the exported JSON records **who validated** each annotation, and
whether **one reviewer per candidate** is required. This must be asked again.

## 3. What the repository already does (verified)

| Area | State | Evidence |
|---|---|---|
| Video upload, container/size/duration validation, ffmpeg probe | **Working** | 56 backend tests; real ffmpeg smoke |
| HTTP Range streaming, real clip extraction | **Working** | smoke: 26/26 checks |
| Asynchronous jobs: queue, worker, retries, cancel, idempotency | **Working** | DB-backed queue, tested |
| Candidates with proposal/preview separation and confidence | **Working** | tested |
| Review: accept/reject (TP/FP), corrections, explicit unreviewed, counters | **Working** | API tested; UI headless E2E reported |
| Dataset export mechanics | **Working but wrong format** | ZIP with `manifest.json` + `labels.csv`; target is OpenLABEL-like JSON |
| Responsive web UI | **Working** (projects, workspace, review) | build + 21 tests; 375 px checked |
| Optional single bearer token | **Working** | tested; not a user/role system |
| Automated tests | 77 total (56 backend + 21 UI), ruff clean | `docs/TEST_PLAN.md` |
| Documentation | 60+ Markdown docs, 4 decks | `docs/`, `presentations/` |

**What this is not:** it is a technical prototype with a **mock** detector. It does not satisfy the v1.1 MVP
scope (accounts, roles, dataset/search model, JSON export, real detection).

## 4. Gap analysis against the v1.1 MVP

| Requirement group | Status | Gap to close |
|---|---|---|
| DS-1…DS-5 datasets/videos | **Partial** | Rename Project→Dataset; MP4-only restriction; enforce 720p/1080p; 5 min Must / 30 min Should; dataset assignment |
| PR-1/PR-2 prompts and searches | **Partial** | Search entity = one prompt over **all videos of a dataset**; prompt history/reuse; multiple searches per dataset |
| DET-1…DET-4 detection | **Missing** | Real zero-shot detector (Gemini API and/or VideoJev-4B); timestamps in minutes:seconds; background status; confidence sorting (exists) |
| REV-1…REV-4 review | **Mostly done** | Thumbnails; "accepted/rejected" vocabulary; review flags (`needs_review`, reasons); one cross-video review list with pagination |
| EXP-1/EXP-2 JSON export | **Missing** | OpenLABEL-based JSON, multiple intervals per action, prompt/model/review status; optional rejected as negatives; async export |
| USR-1…USR-7 accounts | **Missing** | Users, global roles, invitations (48 h single-use), password reset, deactivation, session sign-out/expiry/failed-login lockout |
| NFR-1 desktop browsers | **Partial** | Chrome tested; Firefox/Edge not |
| NFR-2 mobile review | **Partial** | Responsive layout; not tested on Android/iOS |
| NFR-3 processing ≤ 24 h | **Unproven** | Needs real detector and batch run |
| NFR-4 720p/1080p | **Partial** | Accepted but not enforced/tested |
| NFR-5 detection KPIs | **Missing** | No measured precision/recall/complete-clip rate |
| NFR-6 replaceable model | **Done at interface level** | Mock adapter; real backends absent |
| NFR-7 large datasets in one list | **Partial** | Project-wide list exists; no pagination/search scope |
| NFR-8 data protection | **Partial** | Local storage; token; **signed media URLs missing (R-18)**; cloud-API approval pending |
| NFR-9 error handling | **Done** | Job errors + retry |
| NFR-10 deployability | **Partial** | Manual + docs; no Docker/PostgreSQL/Redis/MinIO packaging |
| NFR-11…NFR-14 account security | **Missing** | Hashed passwords, invitation expiry, sign-out, session expiry, lockout |
| ENG-1…ENG-13 detection engine | **Missing** | Windowing, fusion, flags, clips, resume, GPUs profiles — design exists (v1.1 §6.1), no code |

**Reuse plan:** keep and adapt the media pipeline, storage abstraction, job queue, candidate/review model, UI
components and provenance; replace the domain model (Project/Action → Dataset/Search), add auth, and swap the
export format.

## 5. Questions to ask the client tomorrow (priority order)

Each question has a **proposed answer** so the meeting can close points rather than reopen them.

| # | Question | Why it matters | Our proposal / default | Affects |
|---|---|---|---|---|
| **Q1** | **May videos that may show faces be sent to the Gemini API?** If yes, under which conditions (retention, region, anonymisation)? If no, we must self-host. | Blocks the architecture and NFR-8; the key is useless without approval | Run detection on **public/team test videos** via Gemini during development, and use a **self-hosted VideoJev-4B** for customer footage until a written approval exists | NFR-8, DET-1, NFR-6 |
| **Q2** | **Who validated each annotation?** Must the JSON record reviewer identity, and is each candidate reviewed by exactly one person? | The only question from the team's list that was left unanswered; affects data model and export | Record `reviewer` (user id/email) and `reviewed_at`; allow one reviewer per candidate, re-review overwrites with audit trail | USR, REV-3, EXP-1 |
| **Q3** | **What exactly is a "dataset"?** The uploaded-video collection, the labelled output, or both? Can one video belong to several datasets? | The customer's email and our design use "dataset" in both senses; affects model and export | Dataset = **collection of uploaded videos**; export = a **JSON artifact of a dataset + search**; a video belongs to one dataset in the MVP | DS-1/DS-2, EXP-1 |
| **Q4** | **Confirm the JSON structure.** Do you want us to send our OpenLABEL-based proposal before implementing? Do you need **MP4 clips** in the export or only timestamps? | EXP-1 is a Must and the customer asked the team to propose; a wrong schema invalidates the output | Send a one-page schema proposal **by 17 Nov**; export JSON + optional clip files referenced by relative path | EXP-1, EXP-2 |
| **Q5** | **Should rejected candidates be exported as negatives?** | Currently "Could"; affects training data and export schema | Implement if time allows; default **accepted only**, with a flag | EXP-2 |
| **Q6** | **MVP video spec:** 5 minutes at 720p/1080p MP4 now, 30 minutes later — correct? Is audio ever needed? | Drives the detector windowing, storage and acceptance tests | 5 min Must, 30 min Should; **frame-only** MVP; sound-dependent prompts flagged for review | DS-4/DS-5, NFR-4, ENG-6 |
| **Q7** | **Session and sign-in limits:** 2 h inactivity sign-out, 5 failed attempts → 15 min block — acceptable? | Needed for NFR-12…NFR-14 acceptance | Accept as proposed; values configurable | USR-5…USR-7 |
| **Q8** | **Mobile review**: still required? | NFR-2 was in the proposal but not discussed | Keep as **Could**; desktop first | NFR-2 |
| **Q9** | **KPI targets**: complete-clip ≥ 0.85, recall ≥ 0.85, R@IoU 0.5 ≥ 0.70; precision target TBD — acceptable? | NFR-5 acceptance and model choice | Start with these; report precision without a pass/fail threshold until we have data | NFR-5 |
| **Q10** | **Test data**: may we use non-commercial research datasets (Charades-STA) for development/KPIs? Do you have a small sample of customer-like footage (warehouse/driver) we may use? | Licence and realism; Charades-STA videos are **research-only** | Ask for **commercial-use permission or a licensed sample**; otherwise use Charades only for development, not redistribution | NFR-5, NFR-8 |
| **Q11** | **Gemini key/quota**: is the free tier intended for development only? Who owns cost if we exceed it? How should we receive a replacement key (the one sent expires 24 h after 09 Nov)? | Quota and operational continuity | Development on free tier; request budget only if needed; key rotated via secure channel | NFR-3, NFR-8 |
| **Q12** | **Hosting and compute**: who provides the server/database, and is a 12 GB laptop sufficient or do we plan a 24 GB GPU/cloud? | Deployment and NFR-10; supervisors are waiting for our answer | Propose: **Gemini API for development**, **self-hosted 12 GB laptop for the demo**, Docker Compose deployment; escalate a 24 GB GPU request only if KPIs fail | NFR-10, NFR-3 |
| **Q13** | **Deletion/retention**: when must videos and annotations be deleted, and by whom? | Privacy compliance | Add retention settings later; manual delete now | NFR-8 |
| **Q14** | **Access domains**: are accounts limited to Visage email domains, or open invitations? | Security and invitation design | Open invitations with role/dataset scoping; optional domain allow-list | USR-1/5 |

### Questions for the supervisors (separate track)

1. Confirm **remote access** to the 12 GB VRAM laptops (SSH user, public IP, keys) and whether they can be used
   as a server for the course demo.
2. Is **cloud API use** (Gemini) acceptable for the course, given the customer supplied the key?
3. Who provides **hosting** (university vs customer) and a domain?
4. Budget approval if the free tier is insufficient.

## 6. Risks updated by this change

| ID | Risk | Impact |
|---|---|---|
| R-19 | Scope pivot: the new MVP requires accounts/roles/datasets/search/JSON, while the working slice uses projects/actions and a bearer token | High — rework of the domain model and auth |
| R-20 | No written approval to send face-containing videos to Gemini | High — blocks API detector |
| R-21 | Gemini key expiry/leakage; free-tier quota | Medium — operational and security |
| R-22 | Timeline: v1.1 says USR-1…USR-7 are **Must**, but Sprint 2 ends 2026-11-15 | High — MVP gate mismatch |
| R-23 | 12 GB VRAM vs 24 GB assumed for quantised VideoJev-4B | Medium — model choice |
| R-24 | Test-dataset licences are non-commercial | Medium — cannot redistribute results |
| R-25 | OpenLABEL schema mismatch discovered late | Medium — export rework |
| R-26 | Detection quality below KPI targets | High — product risk (customer accepts model limits) |

Full register: `docs/RISK_REGISTER.md`.

## 7. Proposed plan to the MVP (to discuss, not committed)

| Sprint | Dates | Goal |
|---|---|---|
| **2 (closing)** | to 2026-11-15 | Keep the current prototype testable; state clearly it lacks accounts/roles/JSON export. Submit v1 documents on 13 Nov. |
| **3** | 2026-11-16 → 29 | Accounts, global roles, invitations, sessions; Dataset/Search domain model; dataset page; batch search over videos; Gemini-based detector spike; JSON export v0 |
| **4** | 2026-11-30 → 12-13 | Real detector integration (Gemini and/or VideoJev), review flags, KPIs, async JSON export, Docker/PostgreSQL packaging; acceptance test plan |
| **5** | 2026-12-14 → 27 | Hardening, mobile review, acceptance plan finalised before Christmas |
| **6** | 2026-12-28 → 2027-01-10 | Acceptance execution and report, release candidate |
| **7** | 2027-01-11 → 17 | Final report, installation docs, final product |

## 8. Immediate actions and deadlines

| When | Action | Owner |
|---|---|---|
| **Today 2026-11-12** | Review this brief; pick the 6–8 questions that matter most for tomorrow | Product Owner |
| **Today** | Ensure the Gemini key was redeemed; if not, request a new one **without pasting it in chat/repo** | Backend owner |
| **Tomorrow 2026-11-13 23:59** | Submit **Requirements Definition v1** and **Design Description v1** (updated with CE-2) | Requirements/Design owners |
| **Tomorrow** | Client meeting: close Q1–Q5 at minimum; record real answers in `docs/customer/CUSTOMER_DECISIONS.md` | Product Owner |
| **2026-11-16 23:59** | Upload the Status presentation (17 Nov) | Scrum Master |
| **2026-11-17** | Send the customer the one-page JSON schema proposal (Q4) | Architect |
| **2026-11-15** | Sprint 2 close: review/retrospective slides; state MVP limitations honestly | Scrum Master |

## 9. Source documents

| Document | Location | Note |
|---|---|---|
| Requirements Definition v1.1 | `docs/inputs/2026-11-12/VLM_Annotate_-_Requirements_Definition_v1.1.pdf` | 27 FR, 14 NFR, 7 user stories, engine ENG-1…13 |
| Design Description v1.1 | `docs/inputs/2026-11-12/VLM_Annotate_Design_Description_v1.1.pdf` | Architecture, data model, detection engine, API, schema |
| Datasets memo | `docs/inputs/2026-11-12/Datasets.pdf` | Test datasets + licence caveats; **not** the OpenLABEL example |
| Customer decisions | `docs/customer/CUSTOMER_DECISIONS.md` | Transcription of the emails, no secrets |
| Requirements (repo, v1.2) | `docs/REQUIREMENTS.md` | Updated with CE-2 |
| Design (repo, v1.2) | `docs/DESIGN_DESCRIPTION.md` | Updated with CE-2 |
| Risk register | `docs/RISK_REGISTER.md` | R-19…R-26 added |

> **Missing input:** the customer's **OpenLABEL example** itself. Ask for it again; it is referenced by EXP-1
> but is not in this repository. `Datasets.pdf` is a different document (test-dataset selection memo).
