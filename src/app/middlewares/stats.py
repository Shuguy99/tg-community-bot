from aiogram import BaseMiddleware
from aiogram.types import ChatMemberUpdated, Message, TelegramObject


class StatsCollectorMiddleware(BaseMiddleware):
    def __init__(self, buffer):
        self._buffer = buffer

    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = data.get("event_from_user")
        if isinstance(event, Message) and user is not None and event.text is not None:
            self._buffer.record_message(event.chat.id, user.id, event.message_id)
        elif isinstance(event, ChatMemberUpdated):
            old = event.old_chat_member.status
            new = event.new_chat_member.status
            if old in ("left", "kicked") and new in ("member", "administrator", "creator"):
                self._buffer.record_join(event.chat.id)
            elif old in ("member", "administrator", "creator") and new in ("left", "kicked"):
                self._buffer.record_leave(event.chat.id)
        return await handler(event, data)
