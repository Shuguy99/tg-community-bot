from dataclasses import dataclass
from typing import Any


@dataclass
class Deps:
    db: Any
    bot: Any
    state: Any
    outgoing: Any
    subscriptions: Any


_deps: Deps | None = None


def set_deps(deps: Deps) -> None:
    global _deps
    _deps = deps


def get_deps() -> Deps:
    if _deps is None:
        raise RuntimeError("deps not initialized")
    return _deps
