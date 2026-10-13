from aiogram import Router
from aiogram.types import ChatMemberUpdated

from app.handlers.deps import get_deps

provisioning_router = Router(name="provisioning")

ADDED_STATUSES = {"member", "administrator"}
REMOVED_STATUSES = {"left", "kicked"}


@provisioning_router.my_chat_member()
async def on_bot_membership(update: ChatMemberUpdated):
    if update.chat.type == "private":
        return
    deps = get_deps()
    status = update.new_chat_member.status
    if status in ADDED_STATUSES:
        await deps.provisioning.activate(
            update.chat.id, update.chat.type, update.chat.title or ""
        )
    elif status in REMOVED_STATUSES:
        await deps.provisioning.deactivate(update.chat.id)
