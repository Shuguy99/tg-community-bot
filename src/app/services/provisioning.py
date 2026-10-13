import structlog

from app.repositories.chats import ChatRepo

log = structlog.get_logger()


class ProvisioningService:
    def __init__(self, db, bot):
        self._db = db
        self._bot = bot

    async def activate(self, chat_id: int, chat_type: str, title: str) -> None:
        admins = await self._bot.get_chat_administrators(chat_id)
        owner_id = next((a.user.id for a in admins if a.status == "creator"), None)
        try:
            member_count = await self._bot.get_chat_member_count(chat_id)
        except Exception:
            member_count = 0
        async with self._db.session() as session:
            repo = ChatRepo(session)
            await repo.upsert(chat_id, chat_type, title, owner_id, member_count, is_active=True)
            for admin in admins:
                role = "owner" if admin.user.id == owner_id else "admin"
                await repo.add_admin(chat_id, admin.user.id, role)
            await session.commit()
        log.info("chat_activated", chat_id=chat_id, owner_id=owner_id, admins=len(admins))

    async def deactivate(self, chat_id: int) -> None:
        async with self._db.session() as session:
            await ChatRepo(session).set_active(chat_id, False)
            await session.commit()
        log.info("chat_deactivated", chat_id=chat_id)
