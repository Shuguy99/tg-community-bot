from dataclasses import dataclass

from app.antispam.matcher import StopwordMatcher
from app.antispam.rules import (
    Violation,
    ViolationType,
    check_caps,
    check_links,
    check_stopwords,
)
from app.db.models import ChatSettings, ViolationAction
from app.state.redis import StateStore


@dataclass(frozen=True)
class Decision:
    action: ViolationAction
    violation: Violation


async def evaluate(
    *,
    chat_id: int,
    user_id: int,
    text: str,
    settings: ChatSettings,
    matcher: StopwordMatcher,
    state: StateStore,
    is_admin: bool,
) -> Decision | None:
    if is_admin or not settings.antispam_enabled or not text:
        return None

    if await state.is_flood(
        chat_id, user_id, window_sec=settings.flood_window_sec, limit=settings.flood_limit
    ):
        return Decision(settings.action, Violation(ViolationType.FLOOD, "limit exceeded"))

    if settings.delete_duplicates and await state.is_duplicate(
        chat_id, user_id, text, window_sec=settings.flood_window_sec
    ):
        return Decision(settings.action, Violation(ViolationType.DUPLICATE, "repeat"))

    stop = check_stopwords(text, matcher)
    if stop is not None:
        return Decision(settings.action, stop)

    link = check_links(text, enabled=settings.delete_links)
    if link is not None:
        return Decision(settings.action, link)

    caps = check_caps(text, enabled=settings.delete_caps)
    if caps is not None:
        return Decision(settings.action, caps)

    return None
