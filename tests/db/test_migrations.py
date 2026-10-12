import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set",
)


async def test_seed_tiers_present():
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    async with engine.connect() as conn:
        rows = (await conn.execute(text("SELECT plan FROM tier_limits ORDER BY plan"))).all()
    await engine.dispose()
    assert {r[0] for r in rows} == {"corporate", "free", "pro"}
