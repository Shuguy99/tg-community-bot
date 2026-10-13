import pytest
from aiogram.exceptions import TelegramRetryAfter

from app.services.retry import retry_async


async def test_retry_succeeds_after_failures():
    calls = {"n": 0}

    @retry_async(attempts=3, wait_min=0.001, wait_max=0.002)
    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("temporary")
        return "ok"

    assert await flaky() == "ok"
    assert calls["n"] == 3


async def test_retry_gives_up():
    @retry_async(attempts=2, wait_min=0.001, wait_max=0.002)
    async def always():
        raise ConnectionError("nope")

    with pytest.raises(ConnectionError):
        await always()


async def test_retry_on_telegram_retry_after():
    calls = {"n": 0}

    @retry_async(attempts=3, wait_min=0.001, wait_max=0.002)
    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TelegramRetryAfter(method=object(), message="flood", retry_after=0)
        return "ok"

    assert await flaky() == "ok"
    assert calls["n"] == 3
