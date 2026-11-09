from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.scheduler.tasks import sweep_stuck_generations
from .conftest import new_id

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_postprocessing_worker_crash_is_reenqueued(db_engine, as_system, monkeypatch):
    user_id, generation_id = new_id("user"), new_id("gen")
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        await as_system(session)
        await session.execute(text('INSERT INTO auth."user" (id, name, email, credits) VALUES (:id, :id, :email, 100)'), {"id": user_id, "email": f"{user_id}@test.local"})
        await session.execute(text("""INSERT INTO core.ai_model (id, provider, provider_model_id, name, generation_type, pricing_unit, provider_price_usd) VALUES ('recovered-worker-model', 'fal', 'recovered-worker-model', 'Recovered', 'text_to_image', 'image', 0.01) ON CONFLICT (id) DO NOTHING"""))
        await session.execute(text("""INSERT INTO core.generation (id, user_id, type, status, model_id, provider_request_id, estimated_provider_cost_usd, credits_reserved, metadata_json, created_at) VALUES (:gid, :uid, 'text_to_image', 'postprocessing', 'recovered-worker-model', :rid, 0.01, 5, '{"provider_output_url":"https://example.test/output.png"}', :created)"""), {"gid": generation_id, "uid": user_id, "rid": new_id("fal"), "created": datetime.now(timezone.utc) - timedelta(minutes=60)})
        await session.commit()

    calls = []
    async def enqueue(gid): calls.append(gid)
    monkeypatch.setattr("app.scheduler.tasks.enqueue_generation_finalize", enqueue)
    monkeypatch.setattr("app.scheduler.tasks.settings.stuck_generation_minutes", 30)
    result = await sweep_stuck_generations()
    assert generation_id in calls
    assert result["recovered"] >= 1
