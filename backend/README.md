# Vivid Gen Backend — AI Generation Gateway

FastAPI backend for Vivid Gen. The backend is the only service allowed to call fal.ai. The frontend never receives `FAL_KEY`.

## Architecture

- **fal.ai queue + webhooks** own long-running AI inference. This is deliberate: fal's queue is persistent/durable, supports parallel requests, retries, queue status, and webhooks. Vivid Gen therefore does **not** add Inngest or another AI-generation queue in front of fal.
- **FastAPI** is the application gateway: authentication, validation, model routing, pricing, credit reservation, idempotency, and generation state.
- **PostgreSQL** owns users, generations, provider request IDs, credit ledger, and state transitions.
- **S3** owns durable user inputs and final outputs. fal's temporary result/CDN URLs are treated as provider delivery URLs, not the system of record.
- **Redis/ARQ** is only for durable application-side post-processing: downloading completed media, S3 finalization, FFmpeg jobs, thumbnails, waveform extraction, etc. It is intentionally **not** the AI generation queue.
- **FFmpeg** is installed in the container for deterministic media work. Already-valid fal MP4s are not transcoded unnecessarily, keeping generation fast and cheap.
- **Prometheus metrics** are exposed at `/metrics`; health/readiness endpoints are included for load balancers and container orchestration.
- **Fal webhook signatures** are verified against fal's JWKS with a five-minute replay window, and webhook processing is idempotent.
- **Idempotency-Key** is supported on generation endpoints so browser retries do not accidentally create duplicate paid jobs.

## Generation lifecycle

`queued -> processing -> completed`

Failure path:

`queued/processing -> refunded`

Credits are reserved atomically before provider submission. A failed provider request refunds the reservation. Webhooks are idempotent.

## Models and economics

The initial pricing snapshot uses fal's public output pricing observed on 2026-08-19:

| Model | Provider cost | Vivid Gen credits | Customer value at $0.01/credit | Approx. gross margin before ops |
|---|---:|---:|---:|---:|
| Seedream V4 | $0.03/image | 8 | $0.08 | 62.5% |
| Flux Kontext Pro | $0.04/image | 10 | $0.10 | 60.0% |
| Wan 2.5 | $0.05/sec | 5 sec = 63 credits | $0.63 | 60.3% |
| Kling 2.5 Turbo Pro | $0.07/sec | 5 sec = 88 credits | $0.88 | 60.2% |
| Omnihuman 1.5 | $0.16/sec | 15 sec reservation = 600 credits | $6.00 | 60.0% |

The formula is: **retail generation cost = provider cost × 2.5**, then round up to whole credits where **1 credit = $0.01 face value**. A 2.5x cost multiplier is about a 60% gross margin before payment processing, storage, bandwidth, support, taxes, and refunds.

For example, a 5-second Wan 2.5 clip costs fal $0.25. Vivid Gen reserves 63 credits ($0.63 face value), leaving about $0.38 gross contribution before non-fal costs. fal's current pricing page lists Wan 2.5 at $0.05/sec, Kling 2.5 Turbo Pro at $0.07/sec, Seedream V4 at $0.03/image, and Flux Kontext Pro at $0.04/image.

Do **not** hard-code these prices into a customer-facing promise. The model registry is intentionally configurable because fal pricing and model availability can change. Verify the current model price and commercial-use terms before enabling a model in production.

**Pricing is a configurable snapshot, not a guarantee. Verify the model's current price and commercial-use terms before enabling it in production.**

## Setup

1. Copy `.env.example` to `.env`.
2. Put the fal key only in backend `.env`.
3. Set `FAL_WEBHOOK_URL` to a public HTTPS endpoint in production.
4. Run `alembic upgrade head` against the existing Vivid Gen database.
5. Start API: `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
6. Optional worker: `python -m app.worker`.

## Important

Do not commit `.env`. Rotate any credentials that were previously stored in the uploaded project archives.
