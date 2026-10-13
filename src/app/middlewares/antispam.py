from datetime import UTC, datetime, timedelta

import structlog
from aiogram import BaseMiddleware
from aiogram.types import ChatPermissions, Message

from app.antispam.engine import evaluate
from app.db.models import ViolationAction
from app.middlewares.chat_context import ChatContext
from app.repositories.stats import StatsRepo

log = structlog.get_logger()


def resolve_action(action: ViolationAction, warn_count: int, warn_limit: int) -> tuple[ViolationAction, bool]:
    if action == ViolationAction.WARN and warn_count >= warn_limit:
        return ViolationAction.MUTE, False
    if action == ViolationAction.WARN:
        return ViolationAction.WARN, True
    return action, False


class AntiSpamMiddleware(BaseMiddleware):
    def __init__(self, db, state_store, outgoing, bot):
        self._db = db
        self._state = state_store
        self._outgoing = outgoing
        self._bot = bot
        self._warns: dict[tuple[int, int], int] = {}

    async def __call__(self, handler, event: Message, data: dict):
        ctx: ChatContext | None = data.get("ctx")
        user = data.get("event_from_user")
        if ctx is None or user is None or event.text is None:
            return await handler(event, data)
        if event.text.startswith("/"):
            return await handler(event, data)

        decision = await evaluate(
            chat_id=event.chat.id,
            user_id=user.id,
            text=event.text,
            settings=ctx.settings,
            matcher=ctx.matcher,
            state=self._state,
            is_admin=ctx.is_admin,
        )
        if decision is None:
            return await handler(event, data)

        warn_key = (event.chat.id, user.id)
        warn_count = self._warns.get(warn_key, 0) + 1
        action, should_warn = resolve_action(decision.action, warn_count, ctx.settings.warn_limit)
        self._warns[warn_key] = warn_count

        await self._outgoing.submit(lambda: self._bot.delete_message(event.chat.id, event.message_id), priority=0)
        if action == ViolationAction.MUTE:
            until = datetime.now(UTC) + timedelta(minutes=ctx.settings.mute_minutes)
            perms = ChatPermissions(can_send_messages=False)
            await self._outgoing.submit(
                lambda: self._bot.restrict_chat_member(event.chat.id, user.id, perms, until_date=until),
                priority=0,
            )
        elif should_warn:
            await self._outgoing.submit(
                lambda: self._bot.send_message(
                    event.chat.id, f"@{user.username or user.id}, нарушение: {decision.violation.type.value}"
                ),
                priority=5,
            )

        await self._log(event, user.id, decision.violation.type.value)
        return None

    async def _log(self, event: Message, user_id: int, violation: str) -> None:
        async with self._db.session() as session:
            await StatsRepo(session).insert_message_logs(
                [{
                    "chat_id": event.chat.id,
                    "user_id": user_id,
                    "message_id": event.message_id,
                    "is_deleted": True,
                    "violation": violation,
                }]
            )
            await session.commit()
