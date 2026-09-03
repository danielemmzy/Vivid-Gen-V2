"""Run once before a load test: pre-creates N users directly in the
`auth.user` table with a starting credit balance. Necessary because in
the real system users only ever get created by Next.js/better-auth
(Prisma) on signup — the backend never creates one itself — so hitting a
never-seen user_id from Locust would just 500 on "user not found" instead
of exercising the generation path you're actually trying to load-test.

Usage:
    DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55432/vividgen_test \
        python -m loadtest.seed_test_users --count 500 --credits 100000
"""
import argparse
import asyncio
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings


async def seed(count: int, credits: int) -> None:
    engine = create_async_engine(settings.database_url)
    user_ids = [f"loadtest_{uuid.uuid4().hex}" for _ in range(count)]
    async with engine.begin() as conn:
        for user_id in user_ids:
            await conn.execute(
                text('INSERT INTO auth."user" (id, name, email, credits) VALUES (:id, :id, :id || \'@loadtest.local\', :credits) ON CONFLICT DO NOTHING'),
                {"id": user_id, "credits": credits},
            )
    await engine.dispose()

    # locustfile.py reads this list so simulated users hit real, pre-seeded
    # accounts instead of a fresh never-seen user_id on every run.
    with open("loadtest/seeded_users.txt", "w") as f:
        f.write("\n".join(user_ids))
    print(f"Seeded {count} load-test users with {credits} credits each -> loadtest/seeded_users.txt")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--credits", type=int, default=100_000)
    args = parser.parse_args()
    asyncio.run(seed(args.count, args.credits))
