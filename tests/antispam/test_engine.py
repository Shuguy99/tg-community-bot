import fakeredis.aioredis
import pytest

from app.antispam.engine import evaluate
from app.antispam.matcher import StopwordMatcher
from app.antispam.rules import ViolationType
from app.db.models import ChatSettings, ViolationAction
from app.state.redis import StateStore


@pytest.fixture
def store():
    return StateStore(fakeredis.aioredis.FakeRedis(decode_responses=True))


def settings(**kw):
    base = dict(
        antispam_enabled=True,
        delete_links=True,
        delete_caps=True,
        delete_duplicates=True,
        flood_limit=3,
        flood_window_sec=10,
        action=ViolationAction.DELETE,
    )
    base.update(kw)
    return ChatSettings(chat_id=1, **base)


async def test_admin_is_exempt(store):
    d = await evaluate(
        chat_id=1, user_id=1, text="https://spam", settings=settings(),
        matcher=StopwordMatcher.build([]), state=store, is_admin=True,
    )
    assert d is None


async def test_link_triggers_delete(store):
    d = await evaluate(
        chat_id=1, user_id=1, text="https://spam", settings=settings(),
        matcher=StopwordMatcher.build([]), state=store, is_admin=False,
    )
    assert d is not None and d.violation.type == ViolationType.LINK
    assert d.action == ViolationAction.DELETE


async def test_flood_takes_priority_over_link(store):
    cfg = settings(flood_limit=1)
    await evaluate(chat_id=1, user_id=9, text="hi", settings=cfg,
                   matcher=StopwordMatcher.build([]), state=store, is_admin=False)
    d = await evaluate(chat_id=1, user_id=9, text="https://x", settings=cfg,
                       matcher=StopwordMatcher.build([]), state=store, is_admin=False)
    assert d is not None and d.violation.type == ViolationType.FLOOD


async def test_disabled_antispam_allows(store):
    d = await evaluate(
        chat_id=1, user_id=1, text="https://spam", settings=settings(antispam_enabled=False),
        matcher=StopwordMatcher.build([]), state=store, is_admin=False,
    )
    assert d is None
