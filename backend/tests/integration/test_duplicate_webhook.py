"""Chaos-testing Test 4 — duplicate webhook.

fal.ai (like most webhook senders) makes at-least-once delivery
guarantees, not exactly-once — a network retry, a timeout on their side
before our 200 was received, or a manual replay can all deliver the same
webhook multiple times. Sending the identical payload 4 times must
produce exactly ONE state transition, one enqueued finalize job — not
four credit charges or four completed-generation side effects.

This is exactly what app/webhooks/fal.py's WebhookEvent idempotency
record and the `if event_row and event_row.processed: return` early-out
are for; this test is what proves that logic actually holds under a
literal replay, not just in the code's intent.
"""
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.webhooks.fal import handle_fal_webhook
from tests.integration.conftest import new_id

pytestmark = pytest.mark.integration


async def _seed_processing_generation(session, as_system, user_id: str, provider_request_id: str) -> str:
    await as_system(session)
    generation_id = new_id("gen")
    await session.execute(
        text('INSERT INTO auth."user" (id, name, email, credits) VALUES (:id, :id, :id || \'@test.local\', 100)'),
        {"id": user_id},
    )
    await session.execute(
        text('INSERT INTO core.ai_model (id, provider, provider_model_id, name, generation_type, pricing_unit, provider_price_usd) '
             "VALUES ('seed-webhook-model', 'fal', 'seed-webhook-model-provider', 'Seed Model', 'text_to_image', 'image', 0.01) "
             "ON CONFLICT (id) DO NOTHING"),
    )
    await session.execute(
        text('INSERT INTO core.generation (id, user_id, type, status, model_id, provider_request_id, estimated_provider_cost_usd, credits_reserved) '
             "VALUES (:id, :uid, 'text_to_image', 'processing', 'seed-webhook-model', :prid, 0.01, 5)"),
        {"id": generation_id, "uid": user_id, "prid": provider_request_id},
    )
    await session.commit()
    return generation_id


@pytest.mark.asyncio
async def test_same_webhook_delivered_four_times_causes_exactly_one_transition(db_engine, as_system, monkeypatch):
    # The webhook handler enqueues a real ARQ job on success — stub that
    # out so this test only exercises the state-transition/idempotency
    # logic, not a live Redis queue.
    enqueue_calls = []

    async def _fake_enqueue(generation_id: str) -> None:
        enqueue_calls.append(generation_id)

    monkeypatch.setattr("app.webhooks.fal.enqueue_generation_finalize", _fake_enqueue)

    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    user_id = new_id("user")
    provider_request_id = new_id("fal_req")

    async with session_factory() as session:
        generation_id = await _seed_processing_generation(session, as_system, user_id, provider_request_id)

    payload = {
        "request_id": provider_request_id,
        "status": "COMPLETED",
        "payload": {"images": [{"url": "https://example.test/fixture.png", "content_type": "image/png"}]},
    }

    results = []
    for _ in range(4):
        async with session_factory() as session:
            await as_system(session)
            results.append(await handle_fal_webhook(session, payload))

    assert enqueue_calls == [generation_id], (
        f"Expected exactly one finalize enqueue for {generation_id}, got {enqueue_calls} — "
        "the webhook handler processed the same delivery more than once."
    )
    # First delivery does the real transition; the following three must
    # come back marked idempotent rather than re-processing.
    assert results[0].get("queued") is True
    assert all(r.get("idempotent") is True for r in results[1:]), f"Replays were not recognized as idempotent: {results[1:]}"

    async with session_factory() as session:
        await as_system(session)
        event_count = (
            await session.execute(
                text("SELECT COUNT(*) FROM core.webhook_event WHERE provider_event_id = :rid"), {"rid": provider_request_id}
            )
        ).scalar_one()
    assert event_count == 1, f"Expected exactly one webhook_event row for this provider_request_id, found {event_count}"
