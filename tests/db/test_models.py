from app.db.models import Chat, ChatSettings, Plan, TierLimit


def test_models_have_expected_tables():
    assert Chat.__tablename__ == "chats"
    assert ChatSettings.__tablename__ == "chat_settings"
    assert TierLimit.__tablename__ == "tier_limits"
    assert Plan.PRO.value == "pro"
