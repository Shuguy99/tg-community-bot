import re
from dataclasses import dataclass
from enum import Enum

from app.antispam.matcher import StopwordMatcher


class ViolationType(str, Enum):
    FLOOD = "flood"
    DUPLICATE = "duplicate"
    STOPWORD = "stopword"
    LINK = "link"
    CAPS = "caps"


@dataclass(frozen=True)
class Violation:
    type: ViolationType
    detail: str = ""


LINK_RE = re.compile(
    r"(https?://|www\.)\S+|t\.me/\S+|@[A-Za-z0-9_]{4,}",
    re.IGNORECASE,
)


def check_links(text: str, *, enabled: bool, allowed_domains: list[str] | None = None) -> Violation | None:
    if not enabled or not text:
        return None
    allowed = allowed_domains or []
    for match in LINK_RE.finditer(text):
        token = match.group(0)
        if any(d.lower() in token.lower() for d in allowed):
            continue
        return Violation(ViolationType.LINK, token[:64])
    return None


def check_caps(
    text: str, *, enabled: bool, min_len: int = 10, ratio: float = 0.7
) -> Violation | None:
    if not enabled or not text:
        return None
    letters = [c for c in text if c.isalpha()]
    if len(letters) < min_len:
        return None
    upper = sum(1 for c in letters if c.isupper())
    if upper / len(letters) >= ratio:
        return Violation(ViolationType.CAPS, f"{upper}/{len(letters)}")
    return None


def check_stopwords(text: str, matcher: StopwordMatcher) -> Violation | None:
    if not text or matcher is None:
        return None
    hits = matcher.match(text)
    if hits:
        return Violation(ViolationType.STOPWORD, ", ".join(hits[:3]))
    return None
