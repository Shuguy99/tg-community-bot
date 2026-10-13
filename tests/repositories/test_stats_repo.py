import os
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.repositories.stats import StatsRepo

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)


async def test_upsert_chat_daily_is_idempotent_accumulator():
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        repo = StatsRepo(session)
        await repo.upsert_chat_daily([{"chat_id": 5, "date": date(2026, 10, 12), "messages": 3}])
        await repo.upsert_chat_daily([{"chat_id": 5, "date": date(2026, 10, 12), "messages": 4}])
        await session.commit()
        rows = await repo.chat_summary(5, since=date(2026, 10, 1))
    await engine.dispose()
    assert rows[0].messages == 7
