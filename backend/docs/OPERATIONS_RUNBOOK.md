# Vivid Gen V2 operations runbook

This runbook is for the V2 FastAPI/PostgreSQL/Redis stack only. It does not
authorize production changes, migrations, billing, or provider activation.

## First response

1. Check liveness: `GET /health/live`.
2. Check dependencies: `GET /health/ready`.
3. Check the authenticated operational snapshot (`/api/v1/admin/ops`) and
   protected Prometheus metrics (`/metrics` with the configured metrics token).
4. Record the request/correlation ID, safe error code, provider, and job ID.
   Never copy secrets, prompts, signed URLs, or raw user media into an
   incident report.

## Queue, callback, and billing incidents

- Pause paid generation at the deployment/configuration layer if provider
  callbacks, credit reconciliation, or the database are unhealthy.
- Inspect queue age, failed/stuck jobs, webhook failure counters, provider
  health, and ledger reconciliation before retrying anything.
- Retry only through the bounded worker/scheduler paths. Do not replay a
  provider callback by editing rows or issuing a second charge.
- A terminal generation must not reserve or charge credits again. Refunds and
  releases must remain auditable ledger events.

## Database backup and restore

- Identify the exact target environment and database role before running any
  command. Hosted and local databases are separate targets.
- Local backup (run from `backend/`, after confirming the container and target):
  `docker compose exec -T postgres pg_dump -U postgres -d vividgen --format=custom --file=- > vividgen-<timestamp>.dump`.
  Keep the dump outside the repository and record its checksum separately.
- Restore only into an isolated database/copy: `pg_restore --clean --if-exists`
  is permitted there, never against the active development or production
  target. Restore both `core` and `auth`, then verify Alembic
  (`core.alembic_version`) and Prisma migration history independently.
- Run `/health/ready`, focused integration tests, and a read-only table/count
  check against the restored copy before considering it usable. A restore has
  not been verified by this runbook until those checks have actually run.
- Never use reset/drop/force-baseline operations to resolve drift. If the
  target or migration history is unclear, stop and escalate.

## Alerts and thresholds

The following signals already exist in `/metrics` or the operational snapshot;
route them to an owned on-call channel before launch:

- Page when `/health/ready` is not ready for two consecutive checks, or when
  `vivid_rate_limit_redis_errors_total` / `vivid_cache_errors_total` increases.
- Page when any generation or production remains non-terminal beyond
  `stuck_generation_minutes` (currently 30) or the reconciliation sweep's
  recovered/repaired count rises unexpectedly.
- Warn on increases in `vivid_webhook_failed_total`; page on a sustained
  verification failure or webhook lag because callbacks affect user-visible
  status and credit settlement.
- Warn on provider latency/failure or cost anomalies using
  `vivid_provider_request_duration_seconds`, generation failure counters, and
  provider-cost reconciliation variance. The owner must set numeric SLOs from
  the provider's verified limits before enabling paid traffic.
- Alert on non-zero ledger drift, unexpected credit refunds, storage growth,
  or repeated export/render failures. Do not auto-refund or delete media from
  an alert handler.

## Storage and retention

- Keep source and generated objects private; issue short-lived signed URLs only
  after ownership checks.
- Run the existing cleanup scheduler for abandoned uploads and expired
  webhook records. Confirm object deletion and metadata retention against the
  approved policy before enabling a destructive retention job.
- The narrow application permission, if deletion is required, is
  `s3:DeleteObject` on the V2 prefixes only:
  `arn:aws:s3:::<bucket>/uploads/*` and `arn:aws:s3:::<bucket>/generations/*`.
  An AWS lifecycle expiration rule for an approved abandoned-upload prefix is
  the safer alternative when application deletion is not allowed. Never grant
  bucket-wide delete or `s3:*`.
- Preserve source media when deleting or replacing generated outputs unless the
  account deletion policy explicitly requires both to be removed.

## Account export and deletion

- Authenticated users can download a V2 JSON export from the Credits page. It
  is read-only, owner-scoped, and intentionally omits credentials, sessions,
  prompts, signed URLs, and media bytes.
- Do not enable Better Auth account deletion until the owner approves the
  retention period, treatment of active/pending generations, credit refunds,
  legal holds, and whether private source/output media is deleted or retained.
  The deletion workflow must then remove or tombstone both `auth` records and
  all matching `core`/S3 records, with an auditable completion result.

## Required production inputs before launch

Production remains fail-closed until the team supplies and verifies the real
Better Auth secret, database/Redis targets, S3 credentials and retention
policy, Fal/Modal callback secrets and URLs, Polar product/webhook setup,
metrics/alert ownership, and a tested backup/restore destination.
