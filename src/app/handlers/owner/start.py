from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.handlers.deps import get_deps

owner_router = Router(name="owner")


@owner_router.message(CommandStart(), F.chat.type == "private")
async def start(message: Message):
    deps = get_deps()
    async with deps.db.session() as session:
        from app.repositories.chats import ChatRepo

        chats = await ChatRepo(session).list_by_owner(message.from_user.id)
    if not chats:
        await message.answer(
            "Привет! Добавь меня в свой чат как админа с правом удалять сообщения.\n"
            "Для этого нажми кнопку ниже.",
            reply_markup=None,
        )
        return
    lines = ["Твои чаты:"]
    for chat in chats:
        lines.append(f"• {chat.title} (id {chat.id})")
    lines.append("\nОтправь /settings <chat_id> для настройки.")
    await message.answer("\n".join(lines))
