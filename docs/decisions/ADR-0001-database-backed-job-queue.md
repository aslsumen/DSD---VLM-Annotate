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
- A crashed worker can leave a job `running`; until the reaper exists (PB-28), manual retry is required.

## Alternatives rejected

| Option | Why not now |
|---|---|
| Celery + Redis | Two more services, more failure modes, heavier install for students |
| In-process background thread | Dies with the API process; no durability; blocks reloads |
| Cron/script polling the API | No claim semantics, fragile |

## Follow-ups

PB-28 stale-job reaper; PostgreSQL claim variant; job metrics.
