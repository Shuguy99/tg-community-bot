from app.antispam.matcher import StopwordMatcher


def test_matches_any_stopword():
    m = StopwordMatcher.build(["спам", "казино", "скам"])
    assert set(m.match("Заходи в наше КАЗИНО сейчас")) == {"казино"}
    assert m.match("обычное сообщение") == []


def test_empty_matcher_returns_empty():
    assert StopwordMatcher.build([]).match("что угодно") == []
