import pytest
from sqlalchemy import text

from .conftest import new_id

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_rls_hides_other_user_rows_and_allows_system_context(db_session, as_system, as_user):
    user_a, user_b = new_id("user"), new_id("user")
    project_b, generation_b = new_id("proj"), new_id("gen")
    session = db_session
    await as_system(session)
    await session.execute(text("""INSERT INTO core.project (id, user_id, title) VALUES (:pid, :uid, 'Private')"""), {"pid": project_b, "uid": user_b})
    await session.execute(text("""INSERT INTO core.ai_model (id, provider, provider_model_id, name, generation_type, pricing_unit, provider_price_usd) VALUES ('recovered-rls-model', 'fal', 'recovered-rls-model', 'Recovered', 'text_to_image', 'image', 0.01) ON CONFLICT (id) DO NOTHING"""))
    await session.execute(text("""INSERT INTO core.generation (id, user_id, type, status, model_id, project_id, estimated_provider_cost_usd) VALUES (:gid, :uid, 'text_to_image', 'completed', 'recovered-rls-model', :pid, 0.01)"""), {"gid": generation_b, "uid": user_b, "pid": project_b})
    await session.commit()
    await as_user(session, user_a)
    assert (await session.execute(text("SELECT id FROM core.generation"))).first() is None
    await as_system(session)
    assert (await session.execute(text("SELECT id FROM core.generation WHERE id=:id"), {"id": generation_b})).first() is not None
