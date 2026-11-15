# ADR-0006 — Optional shared bearer token instead of user accounts

- **Status:** Accepted for the MVP; revisit before any public deployment
- **Date:** 2026-11-05

## Context

The course deployment is a single trusted team on one host, but uploaded footage is private. A completely
open API is unacceptable even for a demo, while full registration/login/roles would consume Sprint 2–3
capacity that the product needs.

## Decision

- If `VLM_API_TOKEN` is set, every `/api/v1` route except `/health` (and the public media diagnostics)
  requires `Authorization: Bearer <token>`.
- The check runs in HTTP **middleware**, so new routes are protected by default; errors use the standard
  envelope (`401 UNAUTHENTICATED`).
- Comparison uses `secrets.compare_digest`.
- When the variable is unset (local development), the API is open and the UI shows no token field.
- The frontend stores the token in `localStorage` and attaches it to every request.

## Why middleware and not only a router dependency

FastAPI 0.162 / Starlette 1.10 introduced lazy router inclusion; a router-level `dependencies=[...]` on an
included parent router was **not applied** (verified: `GET /projects` returned 200 without a token). Middleware
is enforced regardless of router composition, which is the safer default for a security control.

## Consequences

- One shared secret: no per-user attribution beyond the free-text `reviewer` field.
- No CSRF concern (no cookies, explicit header) and no session management.
- Rotating the token logs everyone out; acceptable for the course.
- Not a substitute for real authn/authz; OPT-06 covers per-user roles.

## Verification

`backend/tests/test_security.py::test_bearer_token_is_enforced_when_configured` (401 without token, 401 with a
wrong token, 200 with the right one, health still public).
