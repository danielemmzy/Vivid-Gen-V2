"""Chaos-testing Test 5 — worker crash.

Simulates: a generation reserved credits, its webhook arrived (so it's
sitting in POSTPROCESSING with the provider's output URL already in
metadata_json), and then the worker that was supposed to finalize it
crashed before finishing — the row is now stuck. The standalone
scheduler's sweep must notice it's been stuck past the threshold and
recover it by re-enqueueing the finalize job — this is the fix described
in scheduler/tasks.py's module docstring; before that fix, a stuck
POSTPROCESSING row in fake/dev mode was invisible to the sweep entirely.

Also covers the sibling case: a generation stuck at PROCESSING (no
webhook ever arrived, submission itself may have half-failed) — under
GENERATION_PROVIDER=fake there's no provider status API to poll, so the
correct, conservative outcome is refund-and-fail, not an indefinite hang.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.scheduler.tasks import sweep_stuck_generations
from tests.integration.conftest import new_id

pytestmark = pytest.mark.integration


async def _seed_generation(session, as_system, *, user_id: str, status: str, credits_reserved: int, stuck_minutes_ago: int, metadata=None) -> str:
    await as_system(session)
    generation_id = new_id("gen")
    stuck_at = datetime.now(timezone.utc) - timedelta(minutes=stuck_minutes_ago)
    await session.execute(
        text('INSERT INTO auth."user" (id, name, email, credits) VALUES (:id, :id, :id || \'@test.local\', 100) ON CONFLICT (id) DO NOTHING'),
        {"id": user_id},
    )
    await session.execute(
        text('INSERT INTO core.ai_model (id, provider, provider_model_id, name, generation_type, pricing_unit, provider_price_usd) '
             "VALUES ('seed-crash-model', 'fal', 'seed-crash-model-provider', 'Seed Model', 'text_to_image', 'image', 0.01) "
             "ON CONFLICT (id) DO NOTHING"),
    )
    await session.execute(
        text(
            'INSERT INTO core.generation (id, user_id, type, status, model_id, provider_request_id, '
            "estimated_provider_cost_usd, credits_reserved, metadata_json, created_at) "
            "VALUES (:id, :uid, 'text_to_image', :status, 'seed-crash-model', :prid, 0.01, :credits, :metadata, :created_at)"
        ),
        {
            "id": generation_id, "uid": user_id, "status": status, "prid": new_id("fal_req"),
            "credits": credits_reserved, "metadata": metadata or {}, "created_at": stuck_at,
        },
    )
    await session.commit()
    return generation_id


@pytest.mark.asyncio
async def test_postprocessing_generation_stuck_from_worker_crash_gets_finalize_reenqueued(db_engine, as_system, monkeypatch):
    enqueue_calls = []

    async def _fake_enqueue(generation_id: str) -> None:
        enqueue_calls.append(generation_id)

    monkeypatch.setattr("app.scheduler.tasks.enqueue_generation_finalize", _fake_enqueue)
    monkeypatch.setattr("app.scheduler.tasks.settings.stuck_generation_minutes", 30)

    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    user_id = new_id("user")

    async with session_factory() as session:
        generation_id = await _seed_generation(
            session, as_system, user_id=user_id, status="postprocessing", credits_reserved=10, stuck_minutes_ago=45,
            metadata={"provider_output_url": "https://example.test/output.png", "provider_content_type": "image/png"},
        )

    result = await sweep_stuck_generations()

    assert generation_id in enqueue_calls, "A POSTPROCESSING generation stuck past the threshold was not re-enqueued for finalization"
    assert result["recovered"] >= 1


@pytest.mark.asyncio
async def test_processing_generation_stuck_with_no_completion_signal_is_refunded(db_engine, as_system, monkeypatch):
    """Fake-provider mode has no status API to poll — a PROCESSING row
    stuck this long has no way to confirm success, so the correct outcome
    is refund, not an indefinite hang with credits still reserved."""
    monkeypatch.setattr("app.scheduler.tasks.settings.stuck_generation_minutes", 30)
    monkeypatch.setattr("app.scheduler.tasks.settings.generation_provider", "fake")

    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    user_id = new_id("user")

    async with session_factory() as session:
        generation_id = await _seed_generation(
            session, as_system, user_id=user_id, status="processing", credits_reserved=15, stuck_minutes_ago=45,
        )

    result = await sweep_stuck_generations()
    assert result["repaired"] >= 1

    async with session_factory() as session:
        await as_system(session)
        row = (await session.execute(text('SELECT status, credits_charged FROM core.generation WHERE id = :id'), {"id": generation_id})).first()
        balance = (await session.execute(text('SELECT credits FROM auth."user" WHERE id = :id'), {"id": user_id})).scalar_one()

    assert row.status == "refunded"
    assert balance == 100, f"Expected the reserved 15 credits to be refunded back to 100, got {balance}"
