from app.keyboards.settings import build_settings_keyboard, parse_callback


def test_parse_callback_valid():
    assert parse_callback("set:-100123:antispam_enabled:on") == (-100123, "antispam_enabled", "on")


def test_build_keyboard_has_toggles():
    kb = build_settings_keyboard(chat_id=-100, settings=None)
    datas = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert any(d.startswith("set:-100:antispam_enabled") for d in datas)
