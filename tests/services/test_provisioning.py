import os

import pytest
from sqlalchemy import select

from app.db.base import Base, Database
from app.db.models import Chat, ChatAdmin
from app.services.provisioning import ProvisioningService

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)


class FakeUser:
    def __init__(self, user_id: int):
        self.id = user_id


class FakeAdmin:
    def __init__(self, user_id: int, status: str = "administrator"):
        self.user = FakeUser(user_id)
        self.status = status


class FakeBot:
    def __init__(self, admins, member_count: int):
        self._admins = admins
        self._member_count = member_count
        self.calls = []

    async def get_chat_administrators(self, chat_id: int):
        self.calls.append(("admins", chat_id))
        return self._admins

    async def get_chat_member_count(self, chat_id: int):
        self.calls.append(("count", chat_id))
        return self._member_count


async def _prepare(db: Database):
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def test_activate_creates_chat_owner_and_admins():
    db = Database(os.environ["TEST_DATABASE_URL"])
    await _prepare(db)
    bot = FakeBot(
        [FakeAdmin(101, status="creator"), FakeAdmin(202), FakeAdmin(303)],
        member_count=42,
    )
    service = ProvisioningService(db, bot)

    await service.activate(chat_id=555, chat_type="supergroup", title="Group")

    async with db.session() as session:
        chat = await session.get(Chat, 555)
        assert chat is not None
        assert chat.owner_id == 101
        assert chat.title == "Group"
        assert chat.member_count == 42
        assert chat.is_active is True
        admins = (
            await session.execute(select(ChatAdmin).where(ChatAdmin.chat_id == 555))
        ).scalars().all()
        roles = {a.user_id: a.role for a in admins}
        assert roles == {101: "owner", 202: "admin", 303: "admin"}
    await db.dispose()


async def test_activate_without_creator_leaves_owner_null():
    db = Database(os.environ["TEST_DATABASE_URL"])
    await _prepare(db)
    bot = FakeBot([FakeAdmin(202)], member_count=5)
    service = ProvisioningService(db, bot)

    await service.activate(chat_id=556, chat_type="supergroup", title="NoCreator")

    async with db.session() as session:
        chat = await session.get(Chat, 556)
        assert chat is not None
        assert chat.owner_id is None
    await db.dispose()


async def test_deactivate_marks_chat_inactive():
    db = Database(os.environ["TEST_DATABASE_URL"])
    await _prepare(db)
    service = ProvisioningService(db, FakeBot([], 0))
    async with db.session() as session:
        session.add(Chat(id=557, type="supergroup", title="G", owner_id=1))
        await session.commit()

    await service.deactivate(557)

    async with db.session() as session:
        chat = await session.get(Chat, 557)
        assert chat.is_active is False
    await db.dispose()
