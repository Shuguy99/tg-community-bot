import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

log = structlog.get_logger()


def create_scheduler(stats_service, subscriptions, buffer, outgoing) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")

    async def flush():
        await stats_service.flush()

    async def flush_if_needed():
        if buffer.pending() >= 500:
            await stats_service.flush()

    scheduler.add_job(flush, "interval", seconds=15, id="flush_stats", max_instances=1)
    scheduler.add_job(flush_if_needed, "interval", seconds=3, id="flush_if_big", max_instances=1)
    scheduler.add_job(stats_service.cleanup_logs, "cron", hour=3, minute=30, id="cleanup_logs", args=[30])
    scheduler.add_job(subscriptions.lifecycle, "cron", hour=0, minute=5, id="subscription_lifecycle")
    scheduler.add_job(subscriptions.detect_orphans, "cron", hour=1, minute=0, id="orphan_scan")
    return scheduler
