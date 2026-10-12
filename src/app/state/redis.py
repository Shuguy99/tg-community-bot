import structlog
from redis.asyncio import Redis

log = structlog.get_logger()


class StateStore:
    def __init__(self, redis: Redis):
        self._redis = redis

    async def ping(self) -> bool:
        try:
            return bool(await self._redis.ping())
        except Exception:
            return False

    async def is_flood(self, chat_id: int, user_id: int, *, window_sec: int, limit: int) -> bool:
        key = f"flood:{chat_id}:{user_id}"
        now = _now_ms()
        cutoff = now - window_sec * 1000
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(key, 0, cutoff)
                pipe.zadd(key, {f"{now}:{_rand()}": now})
                pipe.expire(key, window_sec)
                pipe.zcard(key)
                results = await pipe.execute()
            return int(results[-1]) > limit
        except Exception as exc:
            log.warning("flood_state_unavailable", error=str(exc))
            return False

    async def is_duplicate(self, chat_id: int, user_id: int, text: str, *, window_sec: int) -> bool:
        normalized = " ".join(text.lower().split())[:512]
        if not normalized:
            return False
        key = f"dup:{chat_id}:{user_id}"
        try:
            added = await self._redis.sadd(key, normalized)
            await self._redis.expire(key, window_sec)
            return added == 0
        except Exception as exc:
            log.warning("dup_state_unavailable", error=str(exc))
            return False


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)


def _rand() -> str:
    import uuid

    return uuid.uuid4().hex[:8]
