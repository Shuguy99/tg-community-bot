from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    PreCheckoutQuery,
)

from app.handlers.access import is_owner, owner_chats
from app.handlers.deps import get_deps
from app.keyboards.settings import build_chat_picker

payments_router = Router(name="payments")


def plan_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Pro", callback_data=f"buy:{chat_id}:pro")],
        [InlineKeyboardButton(text="Corporate", callback_data=f"buy:{chat_id}:corporate")],
    ])


@payments_router.message(Command("subscription"), F.chat.type == "private")
async def subscription(message: Message):
    deps = get_deps()
    chats = await owner_chats(deps, message.from_user.id)
    if not chats:
        await message.answer("Сначала добавь бота в чат через /start.")
        return
    if len(chats) == 1:
        await message.answer("Выбери тариф:", reply_markup=plan_keyboard(chats[0].id))
        return
    picker = build_chat_picker([(c.id, c.title or str(c.id)) for c in chats], prefix="sub")
    await message.answer("Выбери чат:", reply_markup=picker)


@payments_router.callback_query(F.data.startswith("sub:"))
async def on_sub_menu(cb: CallbackQuery):
    _, chat_id, _action = cb.data.split(":")
    chat_id = int(chat_id)
    deps = get_deps()
    if not await is_owner(deps, chat_id, cb.from_user.id):
        await cb.answer("Нет доступа", show_alert=True)
        return
    await cb.message.answer("Выбери тариф:", reply_markup=plan_keyboard(chat_id))
    await cb.answer()


@payments_router.callback_query(F.data.startswith("buy:"))
async def buy(cb: CallbackQuery):
    _, chat_id, plan = cb.data.split(":")
    chat_id = int(chat_id)
    deps = get_deps()
    if not await is_owner(deps, chat_id, cb.from_user.id):
        await cb.answer("Нет доступа", show_alert=True)
        return
    link = await deps.stars_provider.create_invoice(chat_id, plan)
    await cb.message.answer(
        f"Оплата тарифа {plan} (30 дней):",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Оплатить", url=link)]]
        ),
    )
    await cb.answer()


@payments_router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    deps = get_deps()
    await deps.stars_provider.handle_pre_checkout(query)


@payments_router.message(F.successful_payment)
async def successful(message: Message):
    deps = get_deps()
    result = await deps.stars_provider.handle_payment(message)
    if result is not None:
        await deps.subscriptions.activate(result)
        await message.answer("Оплата прошла, тариф активирован.")
