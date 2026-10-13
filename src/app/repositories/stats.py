from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import ChatStatsDaily, MessageLog, UserStatsDaily


class StatsRepo:
    def __init__(self, session):
        self.session = session

    async def insert_message_logs(self, rows: list[dict]) -> None:
        if rows:
            await self.session.execute(insert(MessageLog), rows)

    async def cleanup_logs(self, before: datetime) -> int:
        result = await self.session.execute(delete(MessageLog).where(MessageLog.created_at < before))
        return result.rowcount or 0

    async def upsert_chat_daily(self, rows: list[dict]) -> None:
        for row in rows:
            stmt = (
                insert(ChatStatsDaily)
                .values(**row)
                .on_conflict_do_update(
                    index_elements=[ChatStatsDaily.chat_id, ChatStatsDaily.date],
                    set_={
                        "messages": ChatStatsDaily.messages + row.get("messages", 0),
                        "joins": ChatStatsDaily.joins + row.get("joins", 0),
                        "leaves": ChatStatsDaily.leaves + row.get("leaves", 0),
                        "active_users": row.get("active_users", ChatStatsDaily.active_users),
                    },
                )
            )
            await self.session.execute(stmt)

    async def upsert_user_daily(self, rows: list[dict]) -> None:
        for row in rows:
            stmt = (
                insert(UserStatsDaily)
                .values(**row)
                .on_conflict_do_update(
                    index_elements=[UserStatsDaily.chat_id, UserStatsDaily.user_id, UserStatsDaily.date],
                    set_={
                        "messages": UserStatsDaily.messages + row.get("messages", 0),
                        "deleted": UserStatsDaily.deleted + row.get("deleted", 0),
                    },
                )
            )
            await self.session.execute(stmt)

    async def bump_join(self, chat_id: int, day) -> None:
        await self.upsert_chat_daily([{"chat_id": chat_id, "date": day, "joins": 1}])

    async def bump_leave(self, chat_id: int, day) -> None:
        await self.upsert_chat_daily([{"chat_id": chat_id, "date": day, "leaves": 1}])

    async def chat_summary(self, chat_id: int, since) -> list[ChatStatsDaily]:
        result = await self.session.execute(
            select(ChatStatsDaily)
            .where(ChatStatsDaily.chat_id == chat_id, ChatStatsDaily.date >= since)
            .order_by(ChatStatsDaily.date)
        )
        return list(result.scalars())

    async def top_users(self, chat_id: int, since, limit: int = 10) -> list[UserStatsDaily]:
        from sqlalchemy import func

        stmt = (
            select(
                UserStatsDaily.user_id,
                func.sum(UserStatsDaily.messages).label("messages"),
                func.sum(UserStatsDaily.deleted).label("deleted"),
            )
            .where(UserStatsDaily.chat_id == chat_id, UserStatsDaily.date >= since)
            .group_by(UserStatsDaily.user_id)
            .order_by(func.sum(UserStatsDaily.messages).desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).all())
