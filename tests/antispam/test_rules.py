import pytest

from app.antispam.matcher import StopwordMatcher
from app.antispam.rules import ViolationType, check_caps, check_links, check_stopwords


@pytest.mark.parametrize(
    "text,expected",
    [
        ("смотри https://spam.example", True),
        ("пиши t.me/scam_channel", True),
        ("найди меня @username", True),
        ("обычный текст без ссылок", False),
    ],
)
def test_links(text, expected):
    result = check_links(text, enabled=True)
    assert (result is not None) == expected


def test_links_disabled():
    assert check_links("https://x.com", enabled=False) is None


def test_caps_detects_shouting():
    assert check_caps("ЭТО ОЧЕНЬ ГРОМКОЕ СООБЩЕНИЕ", enabled=True) is not None
    assert check_caps("Это обычное сообщение", enabled=True) is None


def test_caps_short_text_ignored():
    assert check_caps("УРА", enabled=True) is None


def test_stopwords():
    m = StopwordMatcher.build(["казино"])
    v = check_stopwords("заходи в казино", m)
    assert v is not None and v.type == ViolationType.STOPWORD
    assert check_stopwords("привет", m) is None
