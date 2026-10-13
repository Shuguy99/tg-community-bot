from app.services.subscriptions import is_over_limit

TIERS = {"free": 1000, "pro": None, "corporate": None}


def test_free_over_limit():
    assert is_over_limit("free", 1500, TIERS) is True
    assert is_over_limit("free", 900, TIERS) is False


def test_paid_never_over_limit():
    assert is_over_limit("pro", 10**9, TIERS) is False
