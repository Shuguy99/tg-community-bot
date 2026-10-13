import os

import pytest

from app.db.base import Base, Database
from app.db.models import Chat, ChatSettings
from app.middlewares.chat_context import ChatContextMiddleware, StopwordCache

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)


class FakeChat:
    id = 901
    type = "supergroup"
    title = "Ctx Group"


class FakeUser:
    id = 777


async def test_group_message_autocreates_chat_and_settings():
    db = Database(os.environ["TEST_DATABASE_URL"])
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    middleware = ChatContextMiddleware(db, StopwordCache(db, ttl=1), ttl=1)
    captured: dict = {}

    async def handler(event, data):
        captured["ctx"] = data.get("ctx")

    data = {"event_chat": FakeChat(), "event_from_user": FakeUser()}
    await middleware(handler, object(), data)

    assert captured["ctx"] is not None
    async with db.session() as session:
        assert await session.get(Chat, 901) is not None
        assert await session.get(ChatSettings, 901) is not None
    await db.dispose()
