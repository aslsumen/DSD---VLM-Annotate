# ADR-0003 — "Unreviewed" is the absence of an annotation

- **Status:** Accepted (normative)
- **Date:** 2026-11-05

## Context

A dataset is only trustworthy if a human chose every label. The most common failure mode in annotation tools
is a default label: candidates that nobody reviewed are exported as negatives, silently poisoning training
data and every metric derived from it.

## Decision

- There is **no** `is_negative` / `label` column on `candidates`.
- `annotations` is a separate table with a verdict domain of exactly `true_positive | false_positive`.
- `review_state` is derived: `reviewed` iff an annotation row exists, else `unreviewed`.
- `DELETE /candidates/{id}/annotation` restores `unreviewed`.
- Export includes only reviewed candidates unless `include_unreviewed=true`; included unreviewed items are
  written with `verdict: "unreviewed"` and `provenance`, never as negatives.
- The UI shows a separate "Unreviewed" filter and counter; it never renders an unreviewed item as negative.

## Consequences

- Impossible-by-construction rather than policy-enforced: no code path can produce a negative label from a
  missing decision.
- Counts are explicit (`reviewed_total`, `unreviewed_total`, `true_positive_total`, `false_positive_total`).
- Exports can be partial; the manifest states exactly what was included.
- Consumers must handle a third `verdict` value when `include_unreviewed` is used.

## Verification

`test_review_labels_and_unreviewed_export_guard`, `test_include_unreviewed_export_is_explicit`,
`test_flow.py` assertions on `review_state`, `DATABASE_SCHEMA.md` invariants.

## Alternatives rejected

| Option | Why not |
|---|---|
| Boolean `is_positive` with default false | Unreviewed becomes negative by accident |
| `verdict` including `unreviewed` in the same column | Blurs the human decision with the absence of one; invites defaults |
| UI-only filtering | The API/export would still leak unlabelled items |
