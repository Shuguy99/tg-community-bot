from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta

import structlog

log = structlog.get_logger()


def aggregate_user_rows(events: list[dict], day: date) -> list[dict]:
    counts: Counter = Counter()
    deleted: Counter = Counter()
    for e in events:
        key = (e["chat_id"], e["user_id"])
        counts[key] += 1
        if e.get("is_deleted"):
            deleted[key] += 1
    return [
        {
            "chat_id": chat_id,
            "user_id": user_id,
            "date": day,
            "messages": count,
            "deleted": deleted[(chat_id, user_id)],
        }
        for (chat_id, user_id), count in counts.items()
    ]


def aggregate_chat_row(events: list[dict], day: date) -> dict:
    keys = {(e["chat_id"], e["user_id"]) for e in events}
    chat_ids = {e["chat_id"] for e in events}
    chat_id = next(iter(chat_ids)) if chat_ids else 0
    return {
        "chat_id": chat_id,
        "date": day,
        "messages": len(events),
        "active_users": len({u for (c, u) in keys if c == chat_id}),
    }


def aggregate_chat_rows(events: list[dict], day: date) -> list[dict]:
    grouped: dict[int, list[dict]] = defaultdict(list)
    for e in events:
        grouped[e["chat_id"]].append(e)
    return [aggregate_chat_row(chat_events, day) for chat_events in grouped.values()]


class StatsBuffer:
    def __init__(self):
        self._messages: list[dict] = []
        self._joins: Counter = Counter()
        self._leaves: Counter = Counter()

    def record_message(self, chat_id, user_id, message_id, is_deleted=False, violation=None):
        self._messages.append(
            {
                "chat_id": chat_id,
                "user_id": user_id,
                "message_id": message_id,
                "is_deleted": is_deleted,
                "violation": violation,
            }
        )

    def record_join(self, chat_id: int):
        self._joins[chat_id] += 1

    def record_leave(self, chat_id: int):
        self._leaves[chat_id] += 1

    def pending(self) -> int:
        return len(self._messages) + sum(self._joins.values()) + sum(self._leaves.values())

    def _drain(self):
        messages, joins, leaves = self._messages, self._joins, self._leaves
        self._messages, self._joins, self._leaves = [], Counter(), Counter()
        return messages, joins, leaves


class StatsService:
    def __init__(self, db, buffer: StatsBuffer):
        self._db = db
        self._buffer = buffer

    async def flush(self) -> int:
        from app.repositories.stats import StatsRepo

        messages, joins, leaves = self._buffer._drain()
        if not messages and not joins and not leaves:
            return 0
        day = datetime.now(UTC).date()
        async with self._db.session() as session:
            repo = StatsRepo(session)
            await repo.insert_message_logs(messages)
            if messages:
                grouped: dict[int, list[dict]] = defaultdict(list)
                for event in messages:
                    grouped[event["chat_id"]].append(event)
                for chat_messages in grouped.values():
                    await repo.upsert_user_daily(aggregate_user_rows(chat_messages, day))
                    await repo.upsert_chat_daily(aggregate_chat_rows(chat_messages, day))
            for chat_id, count in joins.items():
                for _ in range(count):
                    await repo.bump_join(chat_id, day)
            for chat_id, count in leaves.items():
                for _ in range(count):
                    await repo.bump_leave(chat_id, day)
            await session.commit()
        log.info("stats_flushed", messages=len(messages))
        return len(messages)

    async def cleanup_logs(self, days: int = 30) -> int:
        from app.repositories.stats import StatsRepo

        cutoff = datetime.now(UTC) - timedelta(days=days)
        async with self._db.session() as session:
            removed = await StatsRepo(session).cleanup_logs(cutoff)
            await session.commit()
        log.info("logs_cleaned", removed=removed)
        return removed
