import pytest

from app.services.payments.stars import StarsProvider, parse_payload


def test_parse_payload_roundtrip():
    assert parse_payload("123:pro") == (123, "pro")


def test_parse_payload_invalid():
    with pytest.raises(ValueError):
        parse_payload("bad")


def test_stars_provider_name():
    assert StarsProvider.name == "stars"
