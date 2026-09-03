# Chaos & load testing runbook

Companion to the automated suite in `tests/integration/`, `tests/test_redis_failure.py`,
and `tests/test_privilege_escalation_http.py`. Everything here runs against
`GENERATION_PROVIDER=fake` — **zero fal.ai cost** for the entire audit
phase (Tests 1–8). Only after all of this passes does Phase I (one real
generation per type on `fal`) happen — see the architecture plan.

## Setup (once)

```bash
docker compose -f docker-compose.test.yml up -d
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55432/vividgen_test
export TEST_DATABASE_URL=$DATABASE_URL
export REDIS_URL=redis://localhost:56379/0
alembic upgrade head          # applies 0001 + 0002 (RLS) to the test DB
pip install -r requirements-dev.txt
```

## Tests 1–4, automated

```bash
pytest tests/ -m "not integration" -v          # unit suite — no infra needed
pytest tests/integration -m integration -v      # Tests 1, 3, 4, 5 — needs the DB above
```

Test 2 (privilege escalation, full HTTP) lives in
`tests/test_privilege_escalation_http.py` — no DB needed, runs with the
unit suite. Test 6 (Redis failure) lives in `tests/test_redis_failure.py`
— also no live Redis needed, since it mocks the client to raise.

## Test 5, live version — worker actually crashes mid-job

The automated version (`tests/integration/test_worker_crash_reconciliation.py`)
seeds a stuck row directly and proves the scheduler recovers it. To see
the *real* crash-and-restart happen end to end:

1. `docker compose up -d api worker scheduler redis` (against a real or test DB).
2. Set `GENERATION_PROVIDER=fake`, submit a generation via the API.
3. Watch the worker logs until you see it pick up `finalize_generation` —
   then, mid-download, `docker compose kill worker` (a hard kill, not a
   graceful stop, to simulate a real crash rather than a clean shutdown).
4. The generation is now stuck at `postprocessing`. Confirm:
   `SELECT status FROM core.generation WHERE id = '...'` shows `postprocessing`
   and stays there.
5. `docker compose up -d worker` to bring a fresh worker back.
6. Wait up to `RECONCILIATION_INTERVAL_SECONDS` (default 300s — lower it
   in `.env` for faster manual testing, e.g. `RECONCILIATION_INTERVAL_SECONDS=15`)
   for the scheduler to notice and re-enqueue.
7. Confirm the generation reaches `completed` and `credits_charged` is
   correct — not double-charged, not still just `credits_reserved`.

## Test 6, live version — kill Redis mid-traffic

```bash
docker compose -f docker-compose.test.yml stop test-redis
```

While it's down, hit the running API:

- `GET /api/v1/credits/balance` — should still return 200 (rate limiting
  fails open for reads; see `middleware/rate_limit.py`'s module docstring).
- `POST /api/v1/generations/text-to-image` — should return **503**, not
  hang or silently succeed unmetered (rate limiting fails closed for
  generation-submission endpoints).
- `GET /api/v1/models` — should still return 200 with stale-but-correct
  data (cache fails open to the DB-free static catalog; there's no DB
  round-trip needed here anyway since it's static config).

Bring Redis back:

```bash
docker compose -f docker-compose.test.yml start test-redis
```

Confirm generation submission works again within a few seconds (no
manual restart of the API required — the Redis client reconnects on its
own).

## Test 7 — kill Postgres mid-transaction

This is the one genuinely hard to script deterministically (you're racing
a `docker kill` against an in-flight transaction), so it's manual:

1. Submit a generation via the API.
2. Immediately (within the same second) run:
   `docker compose -f docker-compose.test.yml kill test-postgres`
3. Restart it: `docker compose -f docker-compose.test.yml up -d test-postgres`
4. Check the outcome. Acceptable end states:
   - The request itself failed (5xx) and **no** `generation` row exists,
     **no** `credit_transaction` row exists — the reservation transaction
     never committed. This is the expected outcome if the kill landed
     before `GenerationService.create`'s first `await self.session.commit()`.
   - A `generation` row exists in `reserving_credits` or later, AND a
     matching `credit_transaction` reservation exists with the balance
     correctly debited — both committed together, or neither did.
   What must **never** happen: a `credit_transaction` debit exists with
   no corresponding `generation` row, or vice versa — that would mean the
   two writes inside the same transaction (`GenerationService.create`
   adds both the `Generation` row and the reservation before committing)
   somehow landed in different transactions. Check with:
   ```sql
   SELECT g.id, g.status FROM core.generation g
   LEFT JOIN core.credit_transaction ct ON ct.generation_id = g.id AND ct.type = 'GENERATION_RESERVATION'
   WHERE g.status = 'reserving_credits' AND ct.id IS NULL;
   -- must return zero rows
   ```

## Test 8 — load test

```bash
export INTERNAL_API_SECRET=<same value as the running API's .env>
python -m loadtest.seed_test_users --count 500 --credits 100000
locust -f loadtest/locustfile.py --host http://localhost:8000
```

Open http://localhost:8089 and run, in order:

| Stage | Users | Spawn rate | Duration |
|---|---|---|---|
| 1 | 100  | 10/s | until 1,000 requests total |
| 2 | 500  | 25/s | until 5,000 requests total |

While it runs, watch `GET /metrics` (or wire it into a Grafana dashboard)
for:

- `vivid_http_request_duration_seconds` p50/p95/p99 per endpoint
- `vivid_generation_failure_total` — should stay flat; any rise under
  load with `GENERATION_PROVIDER=fake` (which can't genuinely fail on
  the provider side) points at a bug in the app itself, not provider
  flakiness
- Postgres: `SELECT count(*) FROM pg_stat_activity;` approaching
  `DATABASE_POOL_SIZE + DATABASE_MAX_OVERFLOW` indicates the connection
  pool is the bottleneck, not the app logic
- Redis: `redis-cli --latency` for queue/rate-limit latency under load

## After all of this passes

Only then move to Phase I: one real generation per type against
`GENERATION_PROVIDER=fal`, cheapest possible settings — see the earlier
testing guidance (480p/720p, 5s duration, num_images=1, short avatar
audio). Check fal.ai's dashboard spend after each one.
