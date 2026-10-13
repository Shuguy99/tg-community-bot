from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.db.models import Chat, ChatAdmin, ChatSettings


class ChatRepo:
    def __init__(self, session):
        self.session = session

    async def get(self, chat_id: int) -> Chat | None:
        return await self.session.get(Chat, chat_id)

    async def upsert(self, chat_id, type, title, owner_id, member_count) -> Chat:
        stmt = (
            insert(Chat)
            .values(id=chat_id, type=type, title=title, owner_id=owner_id, member_count=member_count)
            .on_conflict_do_update(
                index_elements=[Chat.id],
                set_={"title": title, "member_count": member_count, "type": type},
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()
        return await self.get(chat_id)

    async def set_member_count(self, chat_id: int, count: int) -> None:
        await self.session.execute(update(Chat).where(Chat.id == chat_id).values(member_count=count))

    async def list_by_owner(self, owner_id: int) -> list[Chat]:
        result = await self.session.execute(select(Chat).where(Chat.owner_id == owner_id))
        return list(result.scalars())

    async def transfer_owner(self, chat_id: int, new_owner_id: int) -> None:
        await self.session.execute(update(Chat).where(Chat.id == chat_id).values(owner_id=new_owner_id))

    async def is_admin(self, chat_id: int, user_id: int) -> bool:
        row = await self.session.get(ChatAdmin, (chat_id, user_id))
        return row is not None

    async def add_admin(self, chat_id: int, user_id: int, role: str = "admin") -> None:
        stmt = (
            insert(ChatAdmin)
            .values(chat_id=chat_id, user_id=user_id, role=role)
            .on_conflict_do_nothing(index_elements=[ChatAdmin.chat_id, ChatAdmin.user_id])
        )
        await self.session.execute(stmt)


class SettingsRepo:
    def __init__(self, session):
        self.session = session

    async def get_or_create(self, chat_id: int) -> ChatSettings:
        row = await self.session.get(ChatSettings, chat_id)
        if row is None:
            row = ChatSettings(chat_id=chat_id)
            self.session.add(row)
            await self.session.flush()
        return row

    async def update(self, chat_id: int, **fields) -> ChatSettings:
        await self.get_or_create(chat_id)
        await self.session.execute(update(ChatSettings).where(ChatSettings.chat_id == chat_id).values(**fields))
        await self.session.flush()
        await self.session.refresh(await self.session.get(ChatSettings, chat_id))
        return await self.session.get(ChatSettings, chat_id)
