from app.config import Settings


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("SUPERADMIN_IDS", "1,2")
    s = Settings(_env_file=None)
    assert s.bot_token == "123:abc"
    assert s.redis_url == "redis://localhost:6379/0"
    assert s.superadmin_ids == [1, 2]
