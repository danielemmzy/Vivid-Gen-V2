"""Chaos-testing Test 3 — credit race.

Start a user at 100 credits, fire 100 concurrent requests each trying to
reserve 20, and check the invariant that actually matters: money can't be
created or destroyed. The interesting failure mode this catches isn't
"too many reservations succeeded" in the sense of a wrong count — it's a
lost-update race where two concurrent transactions both read balance=100
before either commits, and both then write balance=80, silently erasing
one of the two reservations. `CreditRepository.get_balance_for_update`'s
`FOR UPDATE` is what's supposed to prevent that by serializing writers on
the same user row; this test is what actually proves it does.
"""
import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.credits.service import CreditService
from app.core.exceptions import InsufficientCreditsError
from tests.integration.conftest import new_id

pytestmark = pytest.mark.integration

STARTING_BALANCE = 100
RESERVATION_AMOUNT = 20
CONCURRENT_REQUESTS = 100


async def _seed_user(session, as_system, user_id: str, credits: int) -> None:
    await as_system(session)
    await session.execute(
        text('INSERT INTO auth."user" (id, name, email, credits) VALUES (:id, :id, :id || \'@test.local\', :credits)'),
        {"id": user_id, "credits": credits},
    )
    await session.commit()


async def _attempt_reservation(db_engine, as_system, user_id: str, generation_id: str) -> str:
    """Each concurrent attempt gets its OWN session/connection — sharing
    one AsyncSession across concurrent tasks is unsafe and would produce
    a false pass/fail unrelated to the actual DB-level race being tested."""
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        await as_system(session)
        try:
            await CreditService(session).reserve(user_id, generation_id, RESERVATION_AMOUNT, "race test reservation")
            await session.commit()
            return "success"
        except InsufficientCreditsError:
            await session.rollback()
            return "insufficient"


@pytest.mark.asyncio
async def test_concurrent_reservations_never_oversell_or_lose_credits(db_engine, as_system):
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    user_id = new_id("user")

    async with session_factory() as session:
        await _seed_user(session, as_system, user_id, STARTING_BALANCE)

    results = await asyncio.gather(
        *[
            _attempt_reservation(db_engine, as_system, user_id, new_id("gen"))
            for _ in range(CONCURRENT_REQUESTS)
        ]
    )

    successes = results.count("success")
    max_possible_successes = STARTING_BALANCE // RESERVATION_AMOUNT  # = 5

    async with session_factory() as session:
        await as_system(session)
        final_balance = (await session.execute(text('SELECT credits FROM auth."user" WHERE id = :id'), {"id": user_id})).scalar_one()

    assert successes <= max_possible_successes, (
        f"{successes} reservations of {RESERVATION_AMOUNT} succeeded against a starting balance of "
        f"{STARTING_BALANCE} — that's {successes * RESERVATION_AMOUNT} credits reserved, more than existed. "
        f"This means FOR UPDATE row locking is not actually serializing concurrent reservations."
    )
    assert final_balance >= 0, f"Balance went negative ({final_balance}) — credits were oversold"
    assert final_balance == STARTING_BALANCE - (successes * RESERVATION_AMOUNT), (
        f"Balance ({final_balance}) doesn't reconcile with successful reservations "
        f"({successes} x {RESERVATION_AMOUNT} = {successes * RESERVATION_AMOUNT} from a starting balance of "
        f"{STARTING_BALANCE}) — credits were created or destroyed somewhere in the concurrent path."
    )

    async with session_factory() as session:
        await as_system(session)
        ledger_sum = (
            await session.execute(text('SELECT COALESCE(SUM(amount), 0) FROM core.credit_transaction WHERE user_id = :id'), {"id": user_id})
        ).scalar_one()
    assert ledger_sum == final_balance - STARTING_BALANCE, "credit_transaction ledger doesn't sum to the net balance change — reserved != charged + refunded + outstanding"
