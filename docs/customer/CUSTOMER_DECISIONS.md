# Customer Decisions — consolidated record

**Purpose:** single place where the customer's written answers are transcribed so requirements and design can be
updated without re-reading the email thread. **No secrets are stored here**: the Gemini API key link is
deliberately omitted.

**Sources**

| Ref | Source | Date |
|---|---|---|
| CP | Customer project proposal | before Oct 2026 |
| CM | Kick-off meeting (summary later confirmed by the customer) | 2026-10-30 |
| CE-1 | Customer email answering the team's requirements questions | 2026-11-05 |
| CE-2 | Customer reply to the 2026-11-07 email (latest) | after 2026-11-07, before 2026-11-10 |
| SUP-1…3 | Supervisor emails on GPU/server infrastructure | 2026-11-04, 11-05, 11-09 |

> CE-2 arrived after Requirements Definition v1.1 was frozen (v1.1 still lists these points as open). Its
> answers therefore belong to **v1.2**.

## 1. Decisions confirmed or changed by CE-1 (2026-11-05)

| Topic | Customer answer | Impact |
|---|---|---|
| Viewer role | Remove it; not important | Only Administrator, Annotator, Dataset Administrator remain |
| Administrator / Annotator permissions | Reasonable as proposed; Annotators must not add videos | Confirmed |
| Dataset Administrator (new role) | Can do almost everything, only on datasets they uploaded or were assigned; sees all Annotators but assigns them only to datasets they can access | New role added in v1.1 |
| Export format | Team proposes the structure; customer attached an OpenLABEL-based example; one action may have several separate time intervals; `type` values are application-defined | EXP-1 must support multiple intervals per action |
| Video summary + keyword tags | Generate automatically for searching/filtering; **lower priority than temporal detection; not part of the MVP**; review/edit has even lower priority | EXP-3/EXP-4 and SRCH-1 are **Could**, not MVP |
| Prompt examples | Temporal activities at different timescales: entering a marked zone, walking through it, putting on a helmet, washing hands | Prompt design and test set |
| Video input (from CM) | MP4, Full HD; initially 5-minute videos, progressively scaling to longer recordings | DS-4 **5 min = Must**, DS-5 **30 min = Should** |
| Accuracy | Prioritised over processing speed | NFR-3 allows up to 24 h for a search |
| Fine-tuning | Not required; zero-shot models are evaluated/configured | ENG-1 training-free; out of scope to train from scratch |

## 2. Decisions from CE-2 (latest customer reply)

These are the **new** answers the team does not yet have in v1.1.

| # | Question asked by the team | Customer answer (paraphrased, keep the meaning) | Required change |
|---|---|---|---|
| 1 | Can a Dataset Administrator create datasets, upload videos and export in their own scope? | **Yes**, a Dataset Administrator can do all of that. | Confirms DS-1, DS-2, PR-1, EXP-1 for Dataset Admin (already marked Yes**) |
| 2 | Is inviting users an Administrator-only action? | **No** — it would be convenient if **Dataset Administrators could also invite users by email**, so they can set up a project without waiting for the global Administrator. | **Change:** permissions table "Invite users" becomes Dataset Admin = **Yes** (within their scope); USR-4/USR-5 updated |
| 3 | Are roles global or per dataset? | **Global roles.** A Dataset Administrator can do everything an Annotator can do **on their own dataset**. In the rare case they must annotate a dataset they do not manage, they create a **new account with the global Annotator role**. | **Resolves open question:** roles are per user, global; no per-dataset role. Add note to USR-2/USR-3/USR-4 |
| 4 | Access flow: (a) email invitation, password, sign in with email; or (b) also choose a username | **Option (a) is sufficient.** Username unnecessary; team may design as it prefers. No extra information needed beyond email, full name, password, optional organization. | **Resolves:** USR-1/USR-5 use email-only sign-in; drop username question |
| 5 | Is the workflow "upload several videos → run a prompt on all → review → export" correct? | **Yes, but not continuously.** A Dataset Administrator uploads several videos and **sometimes later** runs one or more prompts; Annotators review later when they have time. | Confirms asynchronous, batch search over all videos of a dataset, multiple searches per dataset |
| 6 | (Asked in the same thread) Should the exported JSON record **who** validated each annotation? Is each candidate reviewed by **one person only**? | **NOT ANSWERED.** | **Still open** — must be asked again |
| 7 | Gemini API access | Customer sent a **Gemini API key** (Google AI Studio, Free Tier; one-time SnapPwd link, 24 h expiry). Quota context: ~3,600 images per request at 258 tokens/image with Flash models; 1M TPM; 1,500 requests/day. Additional budget possible if insufficient. | Infrastructure now has an **API-based option**; NFR-8 privacy approval still needed before sending customer footage |

> **Security / operational warning.** The key was delivered through a one-time link that expires 24 h after
> 2026-11-09. Do **not** paste that link — or the key — into the repository, chat logs or this document. If it
> was not redeemed in time, ask the customer for a new key. Store it in the backend environment
> (`VLM_GEMINI_API_KEY`), never in Git.

## 3. Decisions from supervisors (SUP)

| Topic | What the supervisors said | Status |
|---|---|---|
| University GPU | **12 GB VRAM laptops available immediately**; remote-access method (SSH/IP/keys) not confirmed yet | Open with IT Helpdesk |
| AWS | Possible but slow to set up | Fallback |
| Advice | Try Google Colab or Ollama for limited experiments | Suggestion |
| Customer resources | Customer had not replied about resource support at the time | Open |

The team's preliminary sizing (sent to supervisors): one 24 GB GPU for quantised inference, 32 GB RAM,
512 GB–1 TB storage, accuracy over speed. This conflicts with the 12 GB laptops, so either the model must be
smaller/quantised further, or cloud/API must be used.

## 4. Open items after CE-2

1. **Traceability of validation** — who validated each annotation; one reviewer per candidate? (Asked, not answered.)
2. **OpenLABEL example** — the customer's example is referenced everywhere, but the actual file is **not in
   this repository**. `docs/inputs/2026-11-12/Datasets.pdf` is a *test-dataset and licence memo*, **not** the
   OpenLABEL export example. Ask the customer to resend the example (or the team must find the attachment).
3. **Privacy approval** for sending videos that may show faces to the Gemini API (NFR-8).
4. **Compute/hosting decision** — Gemini API vs 12 GB laptop vs 24 GB GPU vs AWS; who provides the server.
5. **Meaning of "dataset"** — uploaded-video collection, labelled output, or both; can a video belong to
   more than one dataset?
6. **JSON export fields** — reviewer, review status, fps, prompt, multiple intervals per action, rejected as
   negatives?
7. **Test datasets and licences** — Charades-STA is the best first fit but its underlying videos are
   non-commercial research only; commercial use must be decided.
8. **Session/sign-in limits** — 2 h inactivity; 5 failures → 15 min lock.
9. **KPI targets** — confirm the proposed values.
10. **Mobile review** — still required?
11. **Audio-dependent prompts** — flag for review only, or plan audio later?
12. **Deletion/retention** — when are videos and annotations deleted, and by whom?
