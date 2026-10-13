import time

from app.middlewares.chat_context import TTLCache


def test_ttl_cache_set_get_and_invalidate():
    cache = TTLCache(ttl=60)
    cache.set(1, "a")
    assert cache.get(1) == "a"
    cache.invalidate(1)
    assert cache.get(1) is None


def test_ttl_cache_expires():
    cache = TTLCache(ttl=0)
    cache.set(1, "a")
    time.sleep(0.001)
    assert cache.get(1) is None
