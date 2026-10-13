from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.db.models import ViolationAction
from app.handlers.access import is_owner, owner_chats
from app.handlers.deps import get_deps
from app.keyboards.settings import build_chat_picker, build_settings_keyboard, parse_callback

owner_router = Router(name="owner_settings")


class StopwordStates(StatesGroup):
    waiting_add = State()


TOGGLE_FIELDS = {
    "antispam_enabled": "antispam_enabled",
    "delete_links": "delete_links",
    "delete_caps": "delete_caps",
    "delete_duplicates": "delete_duplicates",
}


async def _load_settings(deps, chat_id: int):
    async with deps.db.session() as session:
        from app.repositories.chats import SettingsRepo

        return await SettingsRepo(session).get_or_create(chat_id)


def _settings_message(chat_id: int, settings) -> tuple[str, InlineKeyboardMarkup]:
    return f"Настройки чата {chat_id}:", build_settings_keyboard(chat_id, settings)


@owner_router.message(Command("settings"), F.chat.type == "private")
async def open_settings(message: Message):
    deps = get_deps()
    parts = (message.text or "").split()
    if len(parts) >= 2 and parts[1].lstrip("-").isdigit():
        chat_id = int(parts[1])
        if not await is_owner(deps, chat_id, message.from_user.id):
            await message.answer("Чат не найден или ты не владелец.")
            return
        settings = await _load_settings(deps, chat_id)
        text, markup = _settings_message(chat_id, settings)
        await message.answer(text, reply_markup=markup)
        return

    chats = await owner_chats(deps, message.from_user.id)
    if not chats:
        await message.answer("Сначала добавь бота в чат через /start.")
        return
    picker = build_chat_picker([(c.id, c.title or str(c.id)) for c in chats], prefix="chat")
    await message.answer("Выбери чат для настройки:", reply_markup=picker)


@owner_router.callback_query(F.data.startswith("chat:"))
async def on_chat_pick(cb: CallbackQuery):
    _, chat_id, _action = cb.data.split(":")
    chat_id = int(chat_id)
    deps = get_deps()
    if not await is_owner(deps, chat_id, cb.from_user.id):
        await cb.answer("Нет доступа", show_alert=True)
        return
    settings = await _load_settings(deps, chat_id)
    text, markup = _settings_message(chat_id, settings)
    await cb.message.answer(text, reply_markup=markup)
    await cb.answer()


@owner_router.callback_query(F.data.startswith("set:"))
async def on_toggle(cb: CallbackQuery):
    chat_id, field, value = parse_callback(cb.data)
    deps = get_deps()
    if not await is_owner(deps, chat_id, cb.from_user.id):
        await cb.answer("Нет доступа", show_alert=True)
        return
    async with deps.db.session() as session:
        from app.repositories.chats import SettingsRepo

        repo = SettingsRepo(session)
        if field in TOGGLE_FIELDS:
            settings = await repo.update(chat_id, **{TOGGLE_FIELDS[field]: value == "on"})
        elif field == "action":
            settings = await repo.update(chat_id, action=ViolationAction(value))
        else:
            settings = await repo.get_or_create(chat_id)
        await session.commit()
    deps.chat_context.invalidate(chat_id)
    await cb.message.edit_reply_markup(reply_markup=build_settings_keyboard(chat_id, settings))
    await cb.answer()


async def _stopword_list_keyboard(chat_id: int, words: list[str]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"❌ {word}", callback_data=f"swd:{chat_id}:{idx}")]
        for idx, word in enumerate(words)
    ]
    rows.append([InlineKeyboardButton(text="➕ Добавить", callback_data=f"sw:{chat_id}:add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@owner_router.callback_query(F.data.startswith("sw:"))
async def on_stopword_menu(cb: CallbackQuery, state: FSMContext):
    _, chat_id, action = cb.data.split(":")
    chat_id = int(chat_id)
    deps = get_deps()
    if not await is_owner(deps, chat_id, cb.from_user.id):
        await cb.answer("Нет доступа", show_alert=True)
        return
    if action == "add":
        await state.set_state(StopwordStates.waiting_add)
        await state.update_data(chat_id=chat_id)
        await cb.message.answer("Отправь слово для добавления в стоп-лист.")
    else:
        async with deps.db.session() as session:
            from app.repositories.stopwords import StopwordRepo

            words = await StopwordRepo(session).list_words(chat_id)
        text = "Стоп-слова:" if words else "Стоп-слов пока нет."
        await cb.message.answer(text, reply_markup=await _stopword_list_keyboard(chat_id, words))
    await cb.answer()


@owner_router.callback_query(F.data.startswith("swd:"))
async def on_stopword_delete(cb: CallbackQuery):
    _, chat_id, idx = cb.data.split(":")
    chat_id, idx = int(chat_id), int(idx)
    deps = get_deps()
    if not await is_owner(deps, chat_id, cb.from_user.id):
        await cb.answer("Нет доступа", show_alert=True)
        return
    async with deps.db.session() as session:
        from app.repositories.stopwords import StopwordRepo

        repo = StopwordRepo(session)
        words = await repo.list_words(chat_id)
        if idx < len(words):
            await repo.remove(chat_id, words[idx])
            await session.commit()
        words = await repo.list_words(chat_id)
    deps.chat_context.invalidate(chat_id)
    await cb.message.edit_reply_markup(reply_markup=await _stopword_list_keyboard(chat_id, words))
    await cb.answer("Удалено")


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
