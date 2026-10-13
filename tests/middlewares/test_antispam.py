# tests/middlewares/test_antispam.py
from app.antispam.rules import Violation, ViolationType
from app.middlewares.antispam import resolve_action
from app.db.models import ViolationAction


def test_resolve_delete():
    action, should_warn = resolve_action(ViolationAction.DELETE, warn_count=10, warn_limit=3)
    assert action == ViolationAction.DELETE and should_warn is False


def test_resolve_warn_escalates_to_mute():
    action, should_warn = resolve_action(ViolationAction.WARN, warn_count=2, warn_limit=3)
    assert action == ViolationAction.WARN and should_warn is True
    action2, should_warn2 = resolve_action(ViolationAction.WARN, warn_count=3, warn_limit=3)
    assert action2 == ViolationAction.MUTE and should_warn2 is False
