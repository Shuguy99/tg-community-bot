from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    PreCheckoutQuery,
)

from app.handlers.deps import get_deps

payments_router = Router(name="payments")


def plan_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Pro", callback_data=f"buy:{chat_id}:pro")],
        [InlineKeyboardButton(text="Corporate", callback_data=f"buy:{chat_id}:corporate")],
    ])


@payments_router.message(Command("subscription"))
async def subscription(message: Message):
    deps = get_deps()
    async with deps.db.session() as session:
        from app.repositories.chats import ChatRepo

        chats = await ChatRepo(session).list_by_owner(message.from_user.id)
    if not chats:
        await message.answer("Сначала добавь бота в чат.")
        return
    await message.answer("Выбери тариф:", reply_markup=plan_keyboard(chats[0].id))


@payments_router.callback_query(F.data.startswith("buy:"))
async def buy(cb: CallbackQuery):
    _, chat_id, plan = cb.data.split(":")
    deps = get_deps()
    link = await deps.stars_provider.create_invoice(int(chat_id), plan)
    await cb.message.answer(f"Оплатить: {link}")
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
