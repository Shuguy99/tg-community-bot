from app.db.models import Chat, ChatSettings, Plan, TierLimit


def test_models_have_expected_tables():
    assert Chat.__tablename__ == "chats"
    assert ChatSettings.__tablename__ == "chat_settings"
    assert TierLimit.__tablename__ == "tier_limits"
    assert Plan.PRO.value == "pro"


def test_enum_labels_are_lowercase_values():
    from app.db.models import ChatSettings, Subscription, TierLimit

    assert Subscription.__table__.c.plan.type.enums == ["free", "pro", "corporate"]
    assert TierLimit.__table__.c.plan.type.enums == ["free", "pro", "corporate"]
    assert ChatSettings.__table__.c.action.type.enums == ["delete", "warn", "mute"]
