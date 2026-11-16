# ADR-0001 — Use the database as the job queue

- **Status:** Accepted
- **Date:** 2026-11-05
- **Deciders:** Backend owner (role), Architect (role)
- **Context:** Long video inference and export must not run inside HTTP requests. The deployment target is a
  single course machine; adding a broker (Redis/RabbitMQ) or Celery introduces services the team must install,
  secure and document.

## Decision

Persist jobs in the `processing_jobs` table. A worker process claims one job with an atomic conditional
update:

```sql
UPDATE processing_jobs
SET status='running', attempts=attempts+1, started_at=now
WHERE id = (SELECT id FROM processing_jobs
            WHERE status='queued' AND available_at <= now
            ORDER BY available_at, id LIMIT 1)
  AND status='queued';
```

A rowcount of 0 means another worker won the race.

## Consequences

- Zero extra infrastructure; job state is queryable by the API and the UI.
- Retries, backoff (`available_at`), progress and errors are plain columns — easy to reason about and test.
- SQLite serialises writers, so throughput is one job at a time; acceptable for the course deployment.
- Multi-worker scaling requires PostgreSQL and `SELECT … FOR UPDATE SKIP LOCKED` (documented path).
- A crashed worker leaves a job `running` until the reaper reclaims it (see the 2026-11-16 amendment).

## Alternatives rejected

| Option | Why not now |
|---|---|
| Celery + Redis | Two more services, more failure modes, heavier install for students |
| In-process background thread | Dies with the API process; no durability; blocks reloads |
| Cron/script polling the API | No claim semantics, fragile |

## Follow-ups

PostgreSQL claim variant; job metrics.

## Amendment 2026-11-16: heartbeat lease

Jobs now run minutes to hours (real VLM in the `videojev` adapter), so a worker dying (OOM kill, power loss)
must not strand a job in `running`.

- **Fencing token = `attempts`.** A worker owns a job while `status='running' AND attempts=<claimed value>`.
  No schema change; liveness is the existing `updated_at`.
- **Every job commit is fenced**: a conditional `UPDATE … SET updated_at` on that predicate runs first, in the
  same transaction as the commit (SQLite write lock, Postgres row lock). Zero rows raises `JobInterrupted`;
  the worker rolls back and drops its result, so a stale worker never overwrites a canceled or reclaimed job.
- **Heartbeat thread** in the worker touches `updated_at` every `VLM_WORKER_HEARTBEAT_SECONDS` (default 30),
  covering silent stretches such as model load.
- **Reaper**: before each claim the worker requeues running jobs not touched for 3 heartbeats
  (`WORKER_LOST`), or fails them (and their export) once `max_attempts` is exhausted, so a job that kills the
  worker every time cannot loop forever. The interval changes only retry latency, never results.
- **Cancel** now covers running jobs; the worker notices at its next fence (one progress tick).
- **Caveat:** `updated_at` is written with the worker's clock, so deployments with several worker hosts need
  synchronized clocks (NTP).
