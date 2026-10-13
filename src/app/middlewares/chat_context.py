import time
from dataclasses import dataclass
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.antispam.matcher import StopwordMatcher


class TTLCache:
    def __init__(self, ttl: int = 60):
        self._ttl = ttl
        self._data: dict[Any, tuple[float, Any]] = {}

    def get(self, key):
        item = self._data.get(key)
        if item is None:
            return None
        expires, value = item
        if expires < time.monotonic():
            self._data.pop(key, None)
            return None
        return value

    def set(self, key, value) -> None:
        self._data[key] = (time.monotonic() + self._ttl, value)

    def invalidate(self, key) -> None:
        self._data.pop(key, None)


class StopwordCache:
    def __init__(self, db, ttl: int = 60):
        self._db = db
        self._cache = TTLCache(ttl)

    async def get(self, chat_id: int) -> StopwordMatcher:
        cached = self._cache.get(chat_id)
        if cached is not None:
            return cached
        from app.repositories.stopwords import StopwordRepo

        async with self._db.session() as session:
            words = await StopwordRepo(session).list_words(chat_id)
        matcher = StopwordMatcher.build(words)
        self._cache.set(chat_id, matcher)
        return matcher

    def invalidate(self, chat_id: int) -> None:
        self._cache.invalidate(chat_id)


@dataclass
class ChatContext:
    chat: Any
    settings: Any
    matcher: StopwordMatcher
    is_admin: bool


class ChatContextMiddleware(BaseMiddleware):
    def __init__(self, db, stopword_cache: StopwordCache, ttl: int = 60):
        self._db = db
        self._stopwords = stopword_cache
        self._settings_cache = TTLCache(ttl)

    def invalidate(self, chat_id: int) -> None:
        self._settings_cache.invalidate(chat_id)
        self._stopwords.invalidate(chat_id)

    async def __call__(self, handler, event: TelegramObject, data: dict):
        chat = data.get("event_chat")
        user = data.get("event_from_user")
        if chat is not None and chat.type in ("group", "supergroup") and user is not None:
            from app.repositories.chats import ChatRepo, SettingsRepo

            async with self._db.session() as session:
                settings = self._settings_cache.get(chat.id)
                if settings is None:
                    settings = await SettingsRepo(session).get_or_create(chat.id)
                    await session.commit()
                    self._settings_cache.set(chat.id, settings)
                is_admin = await ChatRepo(session).is_admin(chat.id, user.id)
            matcher = await self._stopwords.get(chat.id)
            data["ctx"] = ChatContext(chat, settings, matcher, is_admin)
        return await handler(event, data)
