from datetime import date

from app.services.stats_service import aggregate_user_rows


def test_aggregate_user_rows_groups_and_totals():
    events = [
        {"chat_id": 1, "user_id": 10, "is_deleted": False},
        {"chat_id": 1, "user_id": 10, "is_deleted": True},
        {"chat_id": 1, "user_id": 20, "is_deleted": False},
    ]
    rows = aggregate_user_rows(events, day=date(2026, 10, 12))
    by_user = {r["user_id"]: r for r in rows}
    assert by_user[10]["messages"] == 2
    assert by_user[10]["deleted"] == 1
    assert by_user[20]["messages"] == 1


def test_aggregate_chat_rows_counts_active_users():
    from app.services.stats_service import aggregate_chat_row

    row = aggregate_chat_row(events=[
        {"chat_id": 1, "user_id": 10},
        {"chat_id": 1, "user_id": 10},
        {"chat_id": 1, "user_id": 20},
    ], day=date(2026, 10, 12))
    assert row["messages"] == 3
    assert row["active_users"] == 2


def test_aggregate_chat_rows_keeps_chats_separate():
    from app.services.stats_service import aggregate_chat_rows

    rows = aggregate_chat_rows(
        [
            {"chat_id": 1, "user_id": 10},
            {"chat_id": 1, "user_id": 10},
            {"chat_id": 2, "user_id": 20},
        ],
        day=date(2026, 10, 12),
    )
    by_chat = {r["chat_id"]: r for r in rows}
    assert by_chat[1]["messages"] == 2
    assert by_chat[1]["active_users"] == 1
    assert by_chat[2]["messages"] == 1
    assert by_chat[2]["active_users"] == 1
