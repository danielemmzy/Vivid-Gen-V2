import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.webhooks.fal import handle_fal_webhook
from .conftest import new_id

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_duplicate_fal_callback_is_processed_once(db_engine, as_system, monkeypatch):
    user_id, request_id, generation_id = new_id("user"), new_id("fal"), new_id("gen")
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        await as_system(session)
        await session.execute(text('INSERT INTO auth."user" (id, name, email, credits) VALUES (:id, :id, :email, 100)'), {"id": user_id, "email": f"{user_id}@test.local"})
        await session.execute(text("""INSERT INTO core.ai_model (id, provider, provider_model_id, name, generation_type, pricing_unit, provider_price_usd) VALUES ('recovered-fal-model', 'fal', 'recovered-fal-model', 'Recovered', 'text_to_image', 'image', 0.01) ON CONFLICT (id) DO NOTHING"""))
        await session.execute(text("""INSERT INTO core.generation (id, user_id, type, status, model_id, provider_request_id, estimated_provider_cost_usd, credits_reserved) VALUES (:gid, :uid, 'text_to_image', 'processing', 'recovered-fal-model', :rid, 0.01, 5)"""), {"gid": generation_id, "uid": user_id, "rid": request_id})
        await session.commit()

    calls = []
    async def enqueue(gid): calls.append(gid)
    monkeypatch.setattr("app.webhooks.fal.enqueue_generation_finalize", enqueue)
    payload = {"request_id": request_id, "status": "COMPLETED", "payload": {"images": [{"url": "https://example.test/output.png"}]}}
    results = []
    for _ in range(4):
        async with factory() as session:
            await as_system(session)
            results.append(await handle_fal_webhook(session, payload))

    assert calls == [generation_id]
    assert results[0]["queued"] is True
    assert all(result.get("idempotent") is True for result in results[1:])
