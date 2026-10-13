from datetime import UTC, datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from app.handlers.deps import get_deps

stats_router = Router(name="stats")

PERIODS = {"day": 1, "week": 7, "month": 30}


@stats_router.message(Command("stats"), F.text.endswith("chart"))
async def cmd_stats_chart(message: Message):
    deps = get_deps()
    if not await deps.subscriptions.has_feature(message.chat.id, "charts"):
        await message.answer("Графики доступны на тарифе Pro. /subscription")
        return
    since = datetime.now(UTC).date() - timedelta(days=30)
    async with deps.db.session() as session:
        from app.repositories.stats import StatsRepo

        rows = await StatsRepo(session).chat_summary(message.chat.id, since=since)
    from app.services.charts import render_growth_chart

    photo = BufferedInputFile(render_growth_chart(rows), filename="growth.png")
    await message.answer_photo(photo)


@stats_router.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.chat.type == "private":
        await message.answer("Открой /stats в чате, где добавлен бот.")
        return
    deps = get_deps()
    since = datetime.now(UTC).date() - timedelta(days=30)
    async with deps.db.session() as session:
        from app.repositories.stats import StatsRepo

        rows = await StatsRepo(session).chat_summary(message.chat.id, since=since)
    from app.services.charts import format_chat_summary

    await message.answer(format_chat_summary(rows))


@stats_router.message(Command("top"))
async def cmd_top(message: Message):
    if message.chat.type == "private":
        await message.answer("Открой /top в чате.")
        return
    period = "week"
    parts = (message.text or "").split()
    if len(parts) > 1 and parts[1] in PERIODS:
        period = parts[1]
    since = datetime.now(UTC).date() - timedelta(days=PERIODS[period])
    deps = get_deps()
    async with deps.db.session() as session:
        from app.repositories.stats import StatsRepo

        rows = await StatsRepo(session).top_users(message.chat.id, since=since, limit=10)
    from app.services.charts import format_top

    await message.answer(format_top(rows))
