import asyncio
import signal
from dataclasses import dataclass

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeDefault
from redis.asyncio import Redis

from app.config import Settings, get_settings
from app.db.base import Database
from app.handlers.deps import Deps, set_deps
from app.handlers.owner.settings import owner_router as owner_settings_router
from app.handlers.owner.start import owner_router as owner_start_router
from app.handlers.payments.stars import payments_router
from app.handlers.provisioning import provisioning_router
from app.handlers.stats import stats_router
from app.logging_setup import configure_logging
from app.middlewares.antispam import AntiSpamMiddleware
from app.middlewares.chat_context import ChatContextMiddleware, StopwordCache
from app.middlewares.stats import StatsCollectorMiddleware
from app.scheduler.jobs import create_scheduler
from app.services.outgoing import OutgoingQueue, TokenBucket
from app.services.payments.stars import StarsProvider
from app.services.provisioning import ProvisioningService
from app.services.stats_service import StatsBuffer, StatsService
from app.services.subscriptions import SubscriptionsService
from app.state.redis import StateStore

log = structlog.get_logger()


def install_middlewares(dp, chat_context, antispam, stats_collector):
    dp.message.outer_middleware(chat_context)
    dp.chat_member.outer_middleware(chat_context)
    dp.message.outer_middleware(antispam)
    dp.message.outer_middleware(stats_collector)
    dp.chat_member.outer_middleware(stats_collector)


@dataclass
class App:
    bot: Bot
    dispatcher: Dispatcher
    db: Database
    scheduler: object
    state: StateStore
    outgoing: OutgoingQueue
    subscriptions: SubscriptionsService
    stats_service: StatsService
    buffer: StatsBuffer
    redis: Redis


async def build_app(settings: Settings) -> App:
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    db = Database(settings.database_url)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    state = StateStore(redis)
    outgoing = OutgoingQueue(TokenBucket(rate=25.0, capacity=25))
    await outgoing.start(n_workers=4)

    tiers = {"free": 1000, "pro": None, "corporate": None}
    prices = {"pro": 500, "corporate": 5000}
    stars = StarsProvider(bot, prices)
    subscriptions = SubscriptionsService(db, bot, stars, tiers)
    provisioning = ProvisioningService(db, bot)
    buffer = StatsBuffer()
    stats_service = StatsService(db, buffer)

    stopword_cache = StopwordCache(db, ttl=60)
    chat_context = ChatContextMiddleware(db, stopword_cache, ttl=60)
    antispam = AntiSpamMiddleware(db, state, outgoing, bot, buffer)
    stats_collector = StatsCollectorMiddleware(buffer)

    dp = Dispatcher()
    install_middlewares(dp, chat_context, antispam, stats_collector)

    for router in (
        owner_start_router,
        owner_settings_router,
        payments_router,
        provisioning_router,
        stats_router,
    ):
        dp.include_router(router)

    scheduler = create_scheduler(stats_service, subscriptions, buffer, outgoing)

    deps = Deps(
        db=db,
        bot=bot,
        state=state,
        outgoing=outgoing,
        subscriptions=subscriptions,
        provisioning=provisioning,
    )
    set_deps(deps)
    deps.chat_context = chat_context
    deps.stars_provider = stars

    return App(bot, dp, db, scheduler, state, outgoing, subscriptions, stats_service, buffer, redis)


async def shutdown(app: App) -> None:
    app.scheduler.shutdown(wait=True)
    await app.stats_service.flush()
    await app.outgoing.stop(drain=True)
    await app.redis.aclose()
    await app.db.dispose()
    await app.bot.session.close()
    log.info("shutdown_complete")


async def set_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Главное меню"),
            BotCommand(command="settings", description="Настройки чата"),
            BotCommand(command="stats", description="Статистика"),
            BotCommand(command="top", description="Топ участников"),
            BotCommand(command="subscription", description="Тариф и оплата"),
        ],
        scope=BotCommandScopeDefault(),
    )
    await bot.set_my_commands(
        [
            BotCommand(command="stats", description="Статистика"),
            BotCommand(command="top", description="Топ участников"),
        ],
        scope=BotCommandScopeAllGroupChats(),
    )


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = await build_app(settings)
    app.scheduler.start()
    await set_commands(app.bot)

    stop = asyncio.Event()

    def _signal(*_):
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal)

    polling = asyncio.create_task(app.dispatcher.start_polling(app.bot))
    try:
        await stop.wait()
        log.info("shutdown_requested")
        await app.dispatcher.stop_polling()
        await polling
    finally:
        await shutdown(app)


if __name__ == "__main__":
    asyncio.run(run())
