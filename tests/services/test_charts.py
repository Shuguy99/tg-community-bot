from datetime import date

from app.services.charts import format_chat_summary, format_top


def test_format_chat_summary():
    rows = [
        type("R", (), {"date": date(2026, 10, 11), "messages": 100, "joins": 5, "leaves": 1, "active_users": 40})(),
        type("R", (), {"date": date(2026, 10, 12), "messages": 50, "joins": 2, "leaves": 0, "active_users": 20})(),
    ]
    text = format_chat_summary(rows)
    assert "150" in text
    assert "7" in text


def test_format_top_lists_users():
    rows = [type("R", (), {"user_id": 10, "messages": 30, "deleted": 2})()]
    text = format_top(rows)
    assert "10" in text and "30" in text
