# ADR-0005 — Local storage behind a storage interface

- **Status:** Accepted
- **Date:** 2026-11-05

## Context

Videos are 1–2 GB for 30 minutes; clips and exports add more. The course deployment is one machine, and the
team has no cloud budget. But the product may later need object storage, and security requires treating
filenames as untrusted.

## Decision

- A `LocalStorage` class owns every filesystem operation: `save_stream`, `path_for`, `delete`, `copy_into`.
- Keys are generated (`videos/{project_id}/{uuid}{ext}`, `clips/...`, `exports/...`); the user filename is
  metadata only.
- `path_for` rejects absolute paths, drive letters, `..` segments and anything resolving outside the root.
- Uploads stream in 1 MiB chunks to a `.part` file, enforce a byte cap, compute SHA-256, then `os.replace`
  atomically.
- `StorageBackend` is a `Protocol` so an S3 implementation can replace `LocalStorage` without touching routes.

## Consequences

- Path traversal is structurally prevented and unit-tested (6 attack strings).
- Partial uploads never appear as finished files.
- Range streaming reads through `path_for`, so it inherits the same guard.
- Local disk growth is unbounded until the purge job exists (R-06).
- Deleting a project must collect keys before the DB cascade, or the files leak; implemented and tested.

## Alternatives rejected

| Option | Why not |
|---|---|
| Store bytes in the database | Bloats backups; poor streaming; SQLite BLOB limits |
| Use the uploaded filename on disk | Collisions, traversal, Unicode issues, information leakage |
| Direct-to-S3 presigned uploads now | Credentials, CORS, cost, and no S3 in the course environment |
