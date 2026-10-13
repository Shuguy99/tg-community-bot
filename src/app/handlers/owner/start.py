from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.handlers.deps import get_deps

owner_router = Router(name="owner")


@owner_router.message(CommandStart(), F.chat.type == "private")
async def start(message: Message):
    deps = get_deps()
    async with deps.db.session() as session:
        from app.repositories.chats import ChatRepo

        chats = await ChatRepo(session).list_by_owner(message.from_user.id)

    me = await deps.bot.get_me()
    add_url = f"https://t.me/{me.username}?startgroup=true"
    add_button = InlineKeyboardButton(text="Добавить в чат", url=add_url)

    if not chats:
        await message.answer(
            "Привет! Добавь меня в свой чат как админа с правом удалять сообщения.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[add_button]]),
        )
        return

    rows = [[add_button]]
    for chat in chats:
        rows.append(
            [InlineKeyboardButton(text=chat.title or str(chat.id), callback_data=f"chat:{chat.id}:settings")]
        )
    await message.answer(
        "Твои чаты — выбери, чтобы открыть настройки:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
