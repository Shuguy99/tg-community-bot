from app.db.base import Base, Database


def test_database_has_base_and_engine():
    db = Database("postgresql+asyncpg://bot:bot@localhost:5432/bot")
    assert db.session_factory is not None
    assert issubclass(Base, object)
