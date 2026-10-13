from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.handlers.deps import get_deps
from app.keyboards.settings import build_settings_keyboard, parse_callback

owner_router = Router(name="owner_settings")


class StopwordStates(StatesGroup):
    waiting_add = State()
    waiting_del = State()


TOGGLE_FIELDS = {
    "antispam_enabled": "antispam_enabled",
    "delete_links": "delete_links",
    "delete_caps": "delete_caps",
    "delete_duplicates": "delete_duplicates",
}


@owner_router.message(Command("settings"))
async def open_settings(message: Message):
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].lstrip("-").isdigit():
        await message.answer("Использование: /settings <chat_id>")
        return
    chat_id = int(parts[1])
    deps = get_deps()
    async with deps.db.session() as session:
        from app.repositories.chats import ChatRepo, SettingsRepo

        chat = await ChatRepo(session).get(chat_id)
        if chat is None or chat.owner_id != message.from_user.id:
            await message.answer("Чат не найден или ты не владелец.")
            return
        settings = await SettingsRepo(session).get_or_create(chat_id)
    await message.answer("Настройки:", reply_markup=build_settings_keyboard(chat_id, settings))


@owner_router.callback_query(F.data.startswith("set:"))
async def on_toggle(cb: CallbackQuery):
    chat_id, field, value = parse_callback(cb.data)
    deps = get_deps()
    if field in TOGGLE_FIELDS:
        new_value = value == "on"
        async with deps.db.session() as session:
            from app.repositories.chats import SettingsRepo

            settings = await SettingsRepo(session).update(chat_id, **{TOGGLE_FIELDS[field]: new_value})
            await session.commit()
        deps.chat_context.invalidate(chat_id)
        await cb.message.edit_reply_markup(reply_markup=build_settings_keyboard(chat_id, settings))
    await cb.answer()


@owner_router.callback_query(F.data.startswith("sw:"))
async def on_stopword_menu(cb: CallbackQuery, state: FSMContext):
    _, chat_id, action = cb.data.split(":")
    chat_id = int(chat_id)
    deps = get_deps()
    if action == "add":
        await state.set_state(StopwordStates.waiting_add)
        await state.update_data(chat_id=chat_id)
        await cb.message.answer("Отправь слово для добавления в стоп-лист.")
    else:
        async with deps.db.session() as session:
            from app.repositories.stopwords import StopwordRepo

            words = await StopwordRepo(session).list_words(chat_id)
        await cb.message.answer("Стоп-слова: " + (", ".join(words) if words else "пусто"))
    await cb.answer()


@owner_router.message(StopwordStates.waiting_add)
async def on_stopword_add(message: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data["chat_id"]
    deps = get_deps()
    word = (message.text or "").strip().lower()
    if word:
        async with deps.db.session() as session:
            from app.repositories.stopwords import StopwordRepo

            await StopwordRepo(session).add(chat_id, word)
            await session.commit()
        deps.chat_context.invalidate(chat_id)
    await state.clear()
    await message.answer(f"Добавлено: {word}" if word else "Пустое слово, отменено.")
