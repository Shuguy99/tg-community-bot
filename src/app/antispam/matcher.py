import re
from collections.abc import Iterable

try:
    import ahocorasick

    _HAS_AHO = True
except ImportError:  # pragma: no cover
    _HAS_AHO = False


class StopwordMatcher:
    def __init__(self, words: list[str], automaton=None, pattern: re.Pattern | None = None):
        self._words = words
        self._automaton = automaton
        self._pattern = pattern

    @classmethod
    def build(cls, words: Iterable[str]) -> "StopwordMatcher":
        cleaned = sorted({w.strip().lower() for w in words if w and w.strip()})
        if not cleaned:
            return cls([])
        if _HAS_AHO:
            auto = ahocorasick.Automaton()
            for w in cleaned:
                auto.add_word(w, w)
            auto.make_automaton()
            return cls(cleaned, automaton=auto)
        pattern = re.compile("|".join(re.escape(w) for w in cleaned), re.IGNORECASE)
        return cls(cleaned, pattern=pattern)

    def match(self, text: str) -> list[str]:
        if not self._words or not text:
            return []
        lowered = text.lower()
        if self._automaton is not None:
            return [word for _, word in self._automaton.iter(lowered)]
        found = {m.group(0).lower() for m in self._pattern.finditer(lowered)}
        return sorted(found)
