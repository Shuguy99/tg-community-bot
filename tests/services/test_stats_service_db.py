import os

import pytest
from sqlalchemy import select

from app.db.base import Base, Database
from app.db.models import UserStatsDaily
from app.services.stats_service import StatsBuffer, StatsService

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)


async def test_deleted_events_are_counted_in_user_stats():
    db = Database(os.environ["TEST_DATABASE_URL"])
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    buffer = StatsBuffer()
    buffer.record_message(8801, 10, 1)
    buffer.record_message(8801, 10, 2, is_deleted=True, violation="links")
    service = StatsService(db, buffer)

    await service.flush()

    async with db.session() as session:
        row = (
            await session.execute(
                select(UserStatsDaily).where(
                    UserStatsDaily.chat_id == 8801, UserStatsDaily.user_id == 10
                )
            )
        ).scalar_one()
        assert row.messages == 2
        assert row.deleted == 1
    await db.dispose()
