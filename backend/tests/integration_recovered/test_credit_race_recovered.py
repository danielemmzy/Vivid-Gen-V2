import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import InsufficientCreditsError
from app.services.credits.service import CreditService
from .conftest import new_id

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_concurrent_reservations_reconcile_without_oversell(db_engine, as_system):
    user_id = new_id("user")
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        await as_system(session)
        await session.execute(text('INSERT INTO auth."user" (id, name, email, credits) VALUES (:id, :id, :email, 100)'), {"id": user_id, "email": f"{user_id}@test.local"})
        await session.commit()

    async def attempt():
        async with factory() as session:
            await as_system(session)
            try:
                await CreditService(session).reserve(user_id, None, 20, "integration race")
                await session.commit()
                return True
            except InsufficientCreditsError:
                await session.rollback()
                return False

    results = await asyncio.gather(*(attempt() for _ in range(20)))
    successes = sum(results)
    async with factory() as session:
        await as_system(session)
        balance = (await session.execute(text('SELECT credits FROM auth."user" WHERE id=:id'), {"id": user_id})).scalar_one()
        ledger = (await session.execute(text("SELECT COALESCE(SUM(amount), 0) FROM core.credit_transaction WHERE user_id=:id"), {"id": user_id})).scalar_one()

    assert successes == 5
    assert balance == 0
    assert ledger == -100
