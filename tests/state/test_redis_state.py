import fakeredis.aioredis
import pytest

from app.state.redis import StateStore


@pytest.fixture
def store():
    return StateStore(fakeredis.aioredis.FakeRedis(decode_responses=True))


async def test_flood_triggers_after_limit(store):
    for _ in range(3):
        assert await store.is_flood(1, 1, window_sec=10, limit=3) is False
    assert await store.is_flood(1, 1, window_sec=10, limit=3) is True


async def test_duplicate_detected(store):
    assert await store.is_duplicate(1, 1, "привет", window_sec=60) is False
    assert await store.is_duplicate(1, 1, "привет", window_sec=60) is True


async def test_redis_error_is_fail_open():
    class Broken:
        async def pipeline(self, *a, **k):
            raise ConnectionError("down")

    store = StateStore(Broken())
    assert await store.is_flood(1, 1, window_sec=10, limit=1) is False
