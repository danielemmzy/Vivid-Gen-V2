"""Chaos-testing Test 1 — RLS attack.

User A and User B each create a Project (and, transitively, a Generation,
Character, Shot, CreditTransaction). Scoped as User A, every direct lookup
of User B's rows must come back empty — not just through the repository's
own `WHERE user_id = ...` filters, but even via a raw, unfiltered
`SELECT * FROM core.generation` that deliberately bypasses application
code entirely. That's the actual thing this test is proving: isolation
enforced by Postgres itself, not just by every call site remembering to
filter correctly.
"""
import pytest
from sqlalchemy import text

from tests.integration.conftest import new_id

pytestmark = pytest.mark.integration


async def _seed_project_with_everything(session, as_system, user_id: str) -> dict[str, str]:
    """Inserts one row into every user-owned table for `user_id`, scoped as
    system (bypassing RLS for the setup itself — a real request would do
    this scoped as the owning user, but system setup here keeps the
    fixture simple and is a legitimate use of the system bypass)."""
    await as_system(session)
    project_id = new_id("proj")
    character_id = new_id("char")
    generation_id = new_id("gen")
    shot_id = new_id("shot")
    txn_id = new_id("txn")

    await session.execute(
        text('INSERT INTO core.project (id, user_id, title, status, aspect_ratio, resolution) '
             "VALUES (:id, :uid, 'Test Project', 'draft', '16:9', '1080p')"),
        {"id": project_id, "uid": user_id},
    )
    await session.execute(
        text('INSERT INTO core.character (id, user_id, project_id, name, reference_s3_keys) '
             "VALUES (:id, :uid, :pid, 'Test Character', '[]')"),
        {"id": character_id, "uid": user_id, "pid": project_id},
    )
    await session.execute(
        text('INSERT INTO core.ai_model (id, provider, provider_model_id, name, generation_type, pricing_unit, provider_price_usd) '
             "VALUES ('seed-test-model', 'fal', 'seed-test-model-provider', 'Seed Test Model', 'text_to_image', 'image', 0.01) "
             "ON CONFLICT (id) DO NOTHING"),
    )
    await session.execute(
        text('INSERT INTO core.generation (id, user_id, type, status, model_id, project_id, estimated_provider_cost_usd, credits_reserved) '
             "VALUES (:id, :uid, 'text_to_image', 'completed', 'seed-test-model', :pid, 0.01, 5)"),
        {"id": generation_id, "uid": user_id, "pid": project_id},
    )
    await session.execute(
        text('INSERT INTO core.shot (id, project_id, order_index, status, prompt, character_ids, generation_id) '
             "VALUES (:id, :pid, 0, 'completed', 'a test shot', :cids, :gid)"),
        {"id": shot_id, "pid": project_id, "cids": f'["{character_id}"]', "gid": generation_id},
    )
    await session.execute(
        text('INSERT INTO core.credit_transaction (id, user_id, generation_id, type, amount, balance_before, balance_after, description) '
             "VALUES (:id, :uid, :gid, 'GENERATION_CHARGE', -5, 100, 95, 'test charge')"),
        {"id": txn_id, "uid": user_id, "gid": generation_id},
    )
    await session.commit()
    return {"project_id": project_id, "character_id": character_id, "generation_id": generation_id, "shot_id": shot_id, "txn_id": txn_id}


@pytest.mark.asyncio
async def test_user_cannot_read_another_users_rows_even_via_unfiltered_select(db_engine, as_system, as_user):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    user_a, user_b = new_id("user"), new_id("user")

    async with session_factory() as setup_session:
        b_rows = await _seed_project_with_everything(setup_session, as_system, user_b)
        await _seed_project_with_everything(setup_session, as_system, user_a)

    # Scoped queries: A explicitly asking for B's specific row IDs.
    async with session_factory() as session:
        await as_user(session, user_a)

        for table, row_id in [
            ("project", b_rows["project_id"]),
            ("generation", b_rows["generation_id"]),
            ("character", b_rows["character_id"]),
            ("shot", b_rows["shot_id"]),
            ("credit_transaction", b_rows["txn_id"]),
        ]:
            result = await session.execute(text(f'SELECT id FROM core."{table}" WHERE id = :id'), {"id": row_id})
            assert result.first() is None, f"User A could see User B's {table} row via a direct ID lookup — RLS is not enforcing isolation"

    # The actual point of this test: an UNFILTERED, un-scoped SELECT * —
    # exactly the "someone forgot a WHERE clause" bug this migration
    # exists to make harmless.
    async with session_factory() as session:
        await as_user(session, user_a)
        result = await session.execute(text('SELECT id, user_id FROM core.generation'))
        rows = result.all()
        seen_user_ids = {r.user_id for r in rows}
        assert user_b not in seen_user_ids, (
            "SELECT * FROM core.generation (no WHERE clause at all) returned User B's rows while "
            "scoped as User A — RLS FORCE policy is not active. Check that migration "
            "0002_row_level_security.py has actually been applied to this database."
        )
        assert all(uid == user_a for uid in seen_user_ids), "Query returned rows belonging to someone other than the scoped user"


@pytest.mark.asyncio
async def test_system_context_bypasses_rls_for_legitimate_cross_user_access(db_engine, as_system):
    """The inverse check: app.is_system_context must actually grant full
    visibility — jobs, the scheduler, and admin tooling depend on this."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    user_a = new_id("user")

    async with session_factory() as setup_session:
        seeded = await _seed_project_with_everything(setup_session, as_system, user_a)

    async with session_factory() as session:
        await as_system(session)
        result = await session.execute(text('SELECT id FROM core.project WHERE id = :id'), {"id": seeded["project_id"]})
        assert result.first() is not None, "System context should see every user's rows, but couldn't find a row that was just inserted"
