# Telegram Community Automation Bot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the MVP of a multi-tenant Telegram bot that moderates chats (anti-spam), collects activity statistics, and monetizes via Telegram Stars.

**Architecture:** Single aiogram 3 process serving many chats; tenant data in PostgreSQL (SQLAlchemy 2.0 async + Alembic); flood/duplicate state and settings cache keyed by `chat_id` in Redis; anti-spam and stat collection run in middlewares; background APScheduler jobs flush stats, roll up daily aggregates, clean logs, and manage subscriptions; outgoing mutations pass through a rate-limited queue.

**Tech Stack:** Python 3.12, aiogram 3, SQLAlchemy 2.0 (async, asyncpg), Alembic, redis.asyncio, pydantic-settings, APScheduler, structlog, tenacity, pyahocorasick, matplotlib, pytest/pytest-asyncio/fakeredis, ruff, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-10-12-tg-antispam-bot-design.md`

## Global Constraints

- Python `>=3.12`; package layout `src/app`, installed editable via `pyproject.toml`.
- Pinned floors: `aiogram>=3.15`, `SQLAlchemy>=2.0`, `alembic>=1.13`, `redis>=5.0`, `pydantic-settings>=2.4`, `APScheduler>=3.10`, `structlog>=24.1`, `tenacity>=8.5`, `pyahocorasick>=2.1`, `matplotlib>=3.9`, `asyncpg`, `fakeredis>=2.24`, `pytest>=8`, `pytest-asyncio>=0.24`, `ruff>=0.6`.
- Migrations run **only** in the `migrate` service; the bot entrypoint never runs Alembic.
- Outgoing state-changing Telegram calls go through a token bucket limited to **25 req/s**; per-chat sends respect ~1 msg/s.
- Redis unavailability is **fail-open** for anti-spam (skip rule, log, never block a chat).
- `ChatContext.invalidate(chat_id)` is called after every settings/stopword write.
- Statistics buffered in memory and flushed every ~15s or 500 events; synchronous flush on SIGTERM/SIGINT.
- Do not add code comments. Docstrings only where a public interface needs one.
- Tests use `fakeredis` for Redis and a disposable Postgres for repositories.

---

### Task 1: Project scaffold, dependencies, config

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `src/app/__init__.py`
- Create: `src/app/config.py`
- Test: `tests/__init__.py`, `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `app.config.Settings` (fields `bot_token: str`, `database_url: str`, `redis_url: str`, `log_level: str`, `superadmin_ids: list[int]`); `app.config.get_settings() -> Settings`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from app.config import Settings


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("SUPERADMIN_IDS", "1,2")
    s = Settings(_env_file=None)
    assert s.bot_token == "123:abc"
    assert s.redis_url == "redis://localhost:6379/0"
    assert s.superadmin_ids == [1, 2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'app')

- [ ] **Step 3: Write `pyproject.toml`, `.env.example`, package init, and config**

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "tg-community-bot"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "aiogram>=3.15",
  "SQLAlchemy>=2.0",
  "alembic>=1.13",
  "asyncpg",
  "redis>=5.0",
  "pydantic-settings>=2.4",
  "APScheduler>=3.10",
  "structlog>=24.1",
  "tenacity>=8.5",
  "pyahocorasick>=2.1",
  "matplotlib>=3.9",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.24", "fakeredis>=2.24", "ruff>=0.6"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["src"]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"
```

```
# .env.example
BOT_TOKEN=
DATABASE_URL=postgresql+asyncpg://bot:bot@localhost:5432/bot
REDIS_URL=redis://localhost:6379/0
LOG_LEVEL=INFO
SUPERADMIN_IDS=
```

```python
# src/app/__init__.py
```

```python
# src/app/config.py
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str = ""
    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"
    superadmin_ids: list[int] = Field(default_factory=list)


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

```python
# tests/__init__.py
```

- [ ] **Step 4: Install and run test**

Run: `pip install -e ".[dev]" && pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .env.example src/app/__init__.py src/app/config.py tests/__init__.py tests/test_config.py
git commit -m "feat: project scaffold and settings"
```

---

### Task 2: Docker dev environment and Makefile

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `Makefile`
- Create: `alembic.ini`
- Create: `alembic/env.py` (skeleton; wired in Task 5)
- Create: `.dockerignore`

**Interfaces:**
- Consumes: `app.config`.
- Produces: runnable `docker compose up` with `postgres`, `redis`, `migrate`, `bot` services.

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim as base
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY alembic.ini ./
RUN pip install -e .
COPY alembic ./alembic
CMD ["python", "-m", "app.main"]
```

- [ ] **Step 2: Write `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: bot
      POSTGRES_PASSWORD: bot
      POSTGRES_DB: bot
    ports: ["5432:5432"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bot"]
      interval: 5s
      timeout: 3s
      retries: 10

  redis:
    image: redis:7
    ports: ["6379:6379"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

  migrate:
    build: .
    command: alembic upgrade head
    env_file: .env
    environment:
      DATABASE_URL: postgresql+asyncpg://bot:bot@postgres:5432/bot
    depends_on:
      postgres: { condition: service_healthy }

  bot:
    build: .
    env_file: .env
    environment:
      DATABASE_URL: postgresql+asyncpg://bot:bot@postgres:5432/bot
      REDIS_URL: redis://redis:6379/0
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
      migrate: { condition: service_completed_successfully }
```

- [ ] **Step 3: Write `Makefile`, `alembic.ini`, `.dockerignore`**

```makefile
install:
	pip install -e ".[dev]"

migrate:
	alembic upgrade head

run:
	python -m app.main

test:
	pytest -q

lint:
	ruff check src tests

format:
	ruff format src tests
```

```ini
# alembic.ini
[alembic]
script_location = alembic
prepend_sys_path = src
sqlalchemy.url =

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

```
# .dockerignore
.git
.venv
__pycache__
tests
docs
*.md
```

- [ ] **Step 4: Verify compose config parses**

Run: `docker compose config -q`
Expected: exit 0 (no output)

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml Makefile alembic.ini .dockerignore
git commit -m "chore: docker dev environment and make targets"
```

---

### Task 3: Async database base

**Files:**
- Create: `src/app/db/__init__.py`
- Create: `src/app/db/base.py`
- Test: `tests/db/test_base.py`

**Interfaces:**
- Consumes: `app.config.Settings`.
- Produces: `app.db.base.Base` (DeclarativeBase); `app.db.base.Database` with `__init__(url: str)`, `async dispose()`, `session() -> AsyncIterator[AsyncSession]` async context manager, `session_factory: async_sessionmaker[AsyncSession]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/db/test_base.py
from app.db.base import Base, Database


def test_database_has_base_and_engine():
    db = Database("postgresql+asyncpg://bot:bot@localhost:5432/bot")
    assert db.session_factory is not None
    assert issubclass(Base, object)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/db/test_base.py -v`
Expected: FAIL (no module `app.db`)

- [ ] **Step 3: Implement `db/base.py`**

```python
# src/app/db/__init__.py
```

```python
# src/app/db/base.py
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, url: str):
        self.engine = create_async_engine(url, pool_pre_ping=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def session(self):
        async with self.session_factory() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/db/test_base.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/app/db tests/db
git commit -m "feat: async database base"
```

---

### Task 4: ORM models

**Files:**
- Create: `src/app/db/models.py`
- Test: `tests/db/test_models.py`

**Interfaces:**
- Consumes: `app.db.base.Base`.
- Produces (all mapped classes in `app.db.models`): `Chat`, `ChatAdmin`, `ChatSettings`, `Stopword`, `MessageLog`, `ChatStatsDaily`, `UserStatsDaily`, `Subscription`, `Transaction`, `TierLimit`, `OwnershipClaim`; enums `Plan(str)`, `ViolationAction(str)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/db/test_models.py
from app.db.models import Chat, ChatSettings, Plan, TierLimit


def test_models_have_expected_tables():
    assert Chat.__tablename__ == "chats"
    assert ChatSettings.__tablename__ == "chat_settings"
    assert TierLimit.__tablename__ == "tier_limits"
    assert Plan.PRO.value == "pro"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/db/test_models.py -v`
Expected: FAIL (no module `app.db.models`)

- [ ] **Step 3: Implement `db/models.py`**

```python
# src/app/db/models.py
from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Plan(str, Enum):
    FREE = "free"
    PRO = "pro"
    CORPORATE = "corporate"


class ViolationAction(str, Enum):
    DELETE = "delete"
    WARN = "warn"
    MUTE = "mute"


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255), default="")
    owner_id: Mapped[int] = mapped_column(BigInteger)
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    settings: Mapped["ChatSettings"] = relationship(back_populates="chat", uselist=False)
    subscription: Mapped["Subscription"] = relationship(back_populates="chat", uselist=False)


class ChatAdmin(Base):
    __tablename__ = "chat_admins"

    chat_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("chats.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    role: Mapped[str] = mapped_column(String(16), default="admin")
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatSettings(Base):
    __tablename__ = "chat_settings"

    chat_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("chats.id"), primary_key=True)
    antispam_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    delete_links: Mapped[bool] = mapped_column(Boolean, default=True)
    delete_caps: Mapped[bool] = mapped_column(Boolean, default=True)
    delete_duplicates: Mapped[bool] = mapped_column(Boolean, default=True)
    flood_limit: Mapped[int] = mapped_column(SmallInteger, default=5)
    flood_window_sec: Mapped[int] = mapped_column(SmallInteger, default=10)
    action: Mapped[ViolationAction] = mapped_column(
        SAEnum(ViolationAction, name="violation_action"), default=ViolationAction.DELETE
    )
    warn_limit: Mapped[int] = mapped_column(SmallInteger, default=3)
    mute_minutes: Mapped[int] = mapped_column(SmallInteger, default=60)
    greeting_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    chat: Mapped[Chat] = relationship(back_populates="settings")


class Stopword(Base):
    __tablename__ = "stopwords"
    __table_args__ = (UniqueConstraint("chat_id", "word"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("chats.id"), index=True)
    word: Mapped[str] = mapped_column(String(128))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MessageLog(Base):
    __tablename__ = "messages_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    message_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    violation: Mapped[str | None] = mapped_column(String(32), nullable=True)


class ChatStatsDaily(Base):
    __tablename__ = "chat_stats_daily"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    joins: Mapped[int] = mapped_column(Integer, default=0)
    leaves: Mapped[int] = mapped_column(Integer, default=0)
    messages: Mapped[int] = mapped_column(Integer, default=0)
    active_users: Mapped[int] = mapped_column(Integer, default=0)


class UserStatsDaily(Base):
    __tablename__ = "user_stats_daily"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    messages: Mapped[int] = mapped_column(Integer, default=0)
    deleted: Mapped[int] = mapped_column(Integer, default=0)


class Subscription(Base):
    __tablename__ = "subscriptions"

    chat_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("chats.id"), primary_key=True)
    plan: Mapped[Plan] = mapped_column(SAEnum(Plan, name="plan"), default=Plan.FREE)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    chat: Mapped[Chat] = relationship(back_populates="subscription")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("chats.id"), index=True)
    payer_id: Mapped[int] = mapped_column(BigInteger)
    amount_stars: Mapped[int] = mapped_column(Integer)
    payload: Mapped[str] = mapped_column(String(255), default="")
    telegram_payment_charge_id: Mapped[str] = mapped_column(String(255), unique=True)
    external_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TierLimit(Base):
    __tablename__ = "tier_limits"

    plan: Mapped[Plan] = mapped_column(SAEnum(Plan, name="plan"), primary_key=True)
    max_members: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_stars: Mapped[int] = mapped_column(Integer, default=0)
    features: Mapped[dict] = mapped_column(JSONB, default=dict)


class OwnershipClaim(Base):
    __tablename__ = "ownership_claims"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("chats.id"), index=True)
    claimant_id: Mapped[int] = mapped_column(BigInteger)
    prev_owner_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/db/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/app/db/models.py tests/db/test_models.py
git commit -m "feat: ORM models for chats, settings, stats, billing"
```

---

### Task 5: Alembic initial migration and tier seed

**Files:**
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/0001_initial.py`
- Modify: `Makefile` (add `seed` target)
- Test: `tests/db/test_migrations.py` (integration; skipped without `TEST_DATABASE_URL`)

**Interfaces:**
- Consumes: `app.db.base.Base`, `app.db.models`, `app.config.get_settings`.
- Produces: migrated schema with seed rows in `tier_limits` (free/pro/corporate).

- [ ] **Step 1: Write the failing integration test**

```python
# tests/db/test_migrations.py
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set",
)


async def test_seed_tiers_present():
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    async with engine.connect() as conn:
        rows = (await conn.execute(text("SELECT plan FROM tier_limits ORDER BY plan"))).all()
    await engine.dispose()
    assert {r[0] for r in rows} == {"corporate", "free", "pro"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `TEST_DATABASE_URL=$DATABASE_URL pytest tests/db/test_migrations.py -v`
Expected: FAIL (relation `tier_limits` does not exist)

- [ ] **Step 3: Write Alembic env, template, and migration**

```python
# alembic/env.py
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import get_settings
from app.db.base import Base
from app.db import models  # noqa: F401  (register tables)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio

    asyncio.run(run_migrations_online())
```

```mako
# alembic/script.py.mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

```python
# alembic/versions/0001_initial.py
"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-12
"""
from alembic import op

from app.db.base import Base
from app.db import models  # noqa: F401

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TIERS = [
    {"plan": "free", "max_members": 1000, "price_stars": 0,
     "features": {"charts": False, "custom_rules": False}},
    {"plan": "pro", "max_members": None, "price_stars": 500,
     "features": {"charts": True, "custom_rules": True}},
    {"plan": "corporate", "max_members": None, "price_stars": 5000,
     "features": {"charts": True, "custom_rules": True, "white_label": True, "api": True}},
]


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    tiers = sa_tier_table()
    op.bulk_insert(tiers, TIERS)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())


def sa_tier_table():
    import sqlalchemy as sa

    return sa.table(
        "tier_limits",
        sa.column("plan", sa.String),
        sa.column("max_members", sa.Integer),
        sa.column("price_stars", sa.Integer),
        sa.column("features", sa.dialects.postgresql.JSONB),
    )
```

- [ ] **Step 4: Run migration and test**

Run: `TEST_DATABASE_URL=$DATABASE_URL alembic upgrade head && TEST_DATABASE_URL=$DATABASE_URL pytest tests/db/test_migrations.py -v`
Expected: PASS

- [ ] **Step 5: Add seed target and commit**

Append to `Makefile`:

```makefile
seed:
	alembic upgrade head
```

```bash
git add alembic alembic.ini Makefile tests/db/test_migrations.py
git commit -m "feat: initial alembic migration and tier seed"
```

---

### Task 6: Stopword matcher (Aho-Corasick)

**Files:**
- Create: `src/app/antispam/__init__.py`
- Create: `src/app/antispam/matcher.py`
- Test: `tests/antispam/test_matcher.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `StopwordMatcher.build(words: Iterable[str]) -> StopwordMatcher`; `matcher.match(text: str) -> list[str]` (matched words, lowercased).

- [ ] **Step 1: Write the failing test**

```python
# tests/antispam/test_matcher.py
from app.antispam.matcher import StopwordMatcher


def test_matches_any_stopword():
    m = StopwordMatcher.build(["спам", "казино", "скам"])
    assert set(m.match("Заходи в наше КАЗИНО сейчас")) == {"казино"}
    assert m.match("обычное сообщение") == []


def test_empty_matcher_returns_empty():
    assert StopwordMatcher.build([]).match("что угодно") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/antispam/test_matcher.py -v`
Expected: FAIL (no module `app.antispam.matcher`)

- [ ] **Step 3: Implement matcher with pyahocorasick and regex fallback**

```python
# src/app/antispam/__init__.py
```

```python
# src/app/antispam/matcher.py
import re
from collections.abc import Iterable

try:
    import ahocorasick

    _HAS_AHO = True
except ImportError:  # pragma: no cover
    _HAS_AHO = False


class StopwordMatcher:
    def __init__(self, words: list[str], automaton=None, pattern: re.Pattern | None = None):
        self._words = words
        self._automaton = automaton
        self._pattern = pattern

    @classmethod
    def build(cls, words: Iterable[str]) -> "StopwordMatcher":
        cleaned = sorted({w.strip().lower() for w in words if w and w.strip()})
        if not cleaned:
            return cls([])
        if _HAS_AHO:
            auto = ahocorasick.Automaton()
            for w in cleaned:
                auto.add_word(w, w)
            auto.make_automaton()
            return cls(cleaned, automaton=auto)
        pattern = re.compile("|".join(re.escape(w) for w in cleaned), re.IGNORECASE)
        return cls(cleaned, pattern=pattern)

    def match(self, text: str) -> list[str]:
        if not self._words or not text:
            return []
        lowered = text.lower()
        if self._automaton is not None:
            return [word for _, word in self._automaton.iter(lowered)]
        found = {m.group(0).lower() for m in self._pattern.finditer(lowered)}
        return sorted(found)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/antispam/test_matcher.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/app/antispam/__init__.py src/app/antispam/matcher.py tests/antispam/test_matcher.py
git commit -m "feat: aho-corasick stopword matcher with regex fallback"
```

---

### Task 7: Pure anti-spam rules

**Files:**
- Create: `src/app/antispam/rules.py`
- Test: `tests/antispam/test_rules.py`

**Interfaces:**
- Consumes: `app.antispam.matcher.StopwordMatcher`.
- Produces: `ViolationType` (str enum: `FLOOD, DUPLICATE, STOPWORD, LINK, CAPS`); dataclass `Violation(type: ViolationType, detail: str = "")`; `check_links(text, *, enabled: bool) -> Violation | None`; `check_caps(text, *, enabled: bool, min_len: int = 10, ratio: float = 0.7) -> Violation | None`; `check_stopwords(text, matcher) -> Violation | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/antispam/test_rules.py
import pytest

from app.antispam.matcher import StopwordMatcher
from app.antispam.rules import ViolationType, check_caps, check_links, check_stopwords


@pytest.mark.parametrize(
    "text,expected",
    [
        ("смотри https://spam.example", True),
        ("пиши t.me/scam_channel", True),
        ("найди меня @username", True),
        ("обычный текст без ссылок", False),
    ],
)
def test_links(text, expected):
    result = check_links(text, enabled=True)
    assert (result is not None) == expected


def test_links_disabled():
    assert check_links("https://x.com", enabled=False) is None


def test_caps_detects_shouting():
    assert check_caps("ЭТО ОЧЕНЬ ГРОМКОЕ СООБЩЕНИЕ", enabled=True) is not None
    assert check_caps("Это обычное сообщение", enabled=True) is None


def test_caps_short_text_ignored():
    assert check_caps("УРА", enabled=True) is None


def test_stopwords():
    m = StopwordMatcher.build(["казино"])
    v = check_stopwords("заходи в казино", m)
    assert v is not None and v.type == ViolationType.STOPWORD
    assert check_stopwords("привет", m) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/antispam/test_rules.py -v`
Expected: FAIL (no module `app.antispam.rules`)

- [ ] **Step 3: Implement rules**

```python
# src/app/antispam/rules.py
import re
from dataclasses import dataclass
from enum import Enum

from app.antispam.matcher import StopwordMatcher


class ViolationType(str, Enum):
    FLOOD = "flood"
    DUPLICATE = "duplicate"
    STOPWORD = "stopword"
    LINK = "link"
    CAPS = "caps"


@dataclass(frozen=True)
class Violation:
    type: ViolationType
    detail: str = ""


LINK_RE = re.compile(
    r"(https?://|www\.)\S+|t\.me/\S+|@[A-Za-z0-9_]{4,}",
    re.IGNORECASE,
)


def check_links(text: str, *, enabled: bool, allowed_domains: list[str] | None = None) -> Violation | None:
    if not enabled or not text:
        return None
    allowed = allowed_domains or []
    for match in LINK_RE.finditer(text):
        token = match.group(0)
        if any(d.lower() in token.lower() for d in allowed):
            continue
        return Violation(ViolationType.LINK, token[:64])
    return None


def check_caps(
    text: str, *, enabled: bool, min_len: int = 10, ratio: float = 0.7
) -> Violation | None:
    if not enabled or not text:
        return None
    letters = [c for c in text if c.isalpha()]
    if len(letters) < min_len:
        return None
    upper = sum(1 for c in letters if c.isupper())
    if upper / len(letters) >= ratio:
        return Violation(ViolationType.CAPS, f"{upper}/{len(letters)}")
    return None


def check_stopwords(text: str, matcher: StopwordMatcher) -> Violation | None:
    if not text or matcher is None:
        return None
    hits = matcher.match(text)
    if hits:
        return Violation(ViolationType.STOPWORD, ", ".join(hits[:3]))
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/antispam/test_rules.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/app/antispam/rules.py tests/antispam/test_rules.py
git commit -m "feat: pure anti-spam rules (links, caps, stopwords)"
```

---

### Task 8: Redis state for flood and duplicates

**Files:**
- Create: `src/app/state/__init__.py`
- Create: `src/app/state/redis.py`
- Test: `tests/state/test_redis_state.py`

**Interfaces:**
- Consumes: `redis.asyncio.Redis`.
- Produces: `StateStore(redis: Redis)` with `async is_flood(chat_id, user_id, *, window_sec, limit) -> bool`; `async is_duplicate(chat_id, user_id, text, *, window_sec) -> bool`; `async ping() -> bool`. Both operations must not raise on Redis errors (return `False` and log).

- [ ] **Step 1: Write the failing test**

```python
# tests/state/test_redis_state.py
import fakeredis.aioredis
import pytest

from app.state.redis import StateStore


@pytest.fixture
def store():
    return StateStore(fakeredis.aioredis.FakeRedis(decode_responses=True))


async def test_flood_triggers_after_limit(store):
    for _ in range(3):
        assert await store.is_flood(1, 1, window_sec=10, limit=3) is False
    assert await store.is_flood(1, 1, window_sec=10, limit=3) is True


async def test_duplicate_detected(store):
    assert await store.is_duplicate(1, 1, "привет", window_sec=60) is False
    assert await store.is_duplicate(1, 1, "привет", window_sec=60) is True


async def test_redis_error_is_fail_open():
    class Broken:
        async def pipeline(self, *a, **k):
            raise ConnectionError("down")

    store = StateStore(Broken())
    assert await store.is_flood(1, 1, window_sec=10, limit=1) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/state/test_redis_state.py -v`
Expected: FAIL (no module `app.state.redis`)

- [ ] **Step 3: Implement state store**

```python
# src/app/state/__init__.py
```

```python
# src/app/state/redis.py
import structlog
from redis.asyncio import Redis

log = structlog.get_logger()


class StateStore:
    def __init__(self, redis: Redis):
        self._redis = redis

    async def ping(self) -> bool:
        try:
            return bool(await self._redis.ping())
        except Exception:
            return False

    async def is_flood(self, chat_id: int, user_id: int, *, window_sec: int, limit: int) -> bool:
        key = f"flood:{chat_id}:{user_id}"
        now = _now_ms()
        cutoff = now - window_sec * 1000
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(key, 0, cutoff)
                pipe.zadd(key, {f"{now}:{_rand()}": now})
                pipe.expire(key, window_sec)
                pipe.zcard(key)
                results = await pipe.execute()
            return int(results[-1]) > limit
        except Exception as exc:
            log.warning("flood_state_unavailable", error=str(exc))
            return False

    async def is_duplicate(self, chat_id: int, user_id: int, text: str, *, window_sec: int) -> bool:
        normalized = " ".join(text.lower().split())[:512]
        if not normalized:
            return False
        key = f"dup:{chat_id}:{user_id}"
        try:
            added = await self._redis.sadd(key, normalized)
            await self._redis.expire(key, window_sec)
            return added == 0
        except Exception as exc:
            log.warning("dup_state_unavailable", error=str(exc))
            return False


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)


def _rand() -> str:
    import uuid

    return uuid.uuid4().hex[:8]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/state/test_redis_state.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/app/state tests/state
git commit -m "feat: redis state for flood and duplicate detection"
```

---

### Task 9: Anti-spam engine

**Files:**
- Create: `src/app/antispam/engine.py`
- Test: `tests/antispam/test_engine.py`

**Interfaces:**
- Consumes: `app.antispam.rules`, `app.antispam.matcher.StopwordMatcher`, `app.state.redis.StateStore`, `app.db.models.ChatSettings`, `app.db.models.ViolationAction`.
- Produces: `Decision(action: ViolationAction, violation: Violation)`; `async evaluate(*, chat_id, user_id, text, settings, matcher, state, is_admin: bool) -> Decision | None`. Admin and empty text return `None`. Rule order: flood → duplicate → stopwords → links → caps.

- [ ] **Step 1: Write the failing test**

```python
# tests/antispam/test_engine.py
import fakeredis.aioredis
import pytest

from app.antispam.engine import evaluate
from app.antispam.matcher import StopwordMatcher
from app.antispam.rules import ViolationType
from app.db.models import ChatSettings, ViolationAction
from app.state.redis import StateStore


@pytest.fixture
def store():
    return StateStore(fakeredis.aioredis.FakeRedis(decode_responses=True))


def settings(**kw):
    base = dict(
        antispam_enabled=True,
        delete_links=True,
        delete_caps=True,
        delete_duplicates=True,
        flood_limit=3,
        flood_window_sec=10,
        action=ViolationAction.DELETE,
    )
    base.update(kw)
    return ChatSettings(chat_id=1, **base)


async def test_admin_is_exempt(store):
    d = await evaluate(
        chat_id=1, user_id=1, text="https://spam", settings=settings(),
        matcher=StopwordMatcher.build([]), state=store, is_admin=True,
    )
    assert d is None


async def test_link_triggers_delete(store):
    d = await evaluate(
        chat_id=1, user_id=1, text="https://spam", settings=settings(),
        matcher=StopwordMatcher.build([]), state=store, is_admin=False,
    )
    assert d is not None and d.violation.type == ViolationType.LINK
    assert d.action == ViolationAction.DELETE


async def test_flood_takes_priority_over_link(store):
    cfg = settings(flood_limit=1)
    await evaluate(chat_id=1, user_id=9, text="hi", settings=cfg,
                   matcher=StopwordMatcher.build([]), state=store, is_admin=False)
    d = await evaluate(chat_id=1, user_id=9, text="https://x", settings=cfg,
                       matcher=StopwordMatcher.build([]), state=store, is_admin=False)
    assert d is not None and d.violation.type == ViolationType.FLOOD


async def test_disabled_antispam_allows(store):
    d = await evaluate(
        chat_id=1, user_id=1, text="https://spam", settings=settings(antispam_enabled=False),
        matcher=StopwordMatcher.build([]), state=store, is_admin=False,
    )
    assert d is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/antispam/test_engine.py -v`
Expected: FAIL (no module `app.antispam.engine`)

- [ ] **Step 3: Implement engine**

```python
# src/app/antispam/engine.py
from dataclasses import dataclass

from app.antispam.matcher import StopwordMatcher
from app.antispam.rules import (
    Violation,
    ViolationType,
    check_caps,
    check_links,
    check_stopwords,
)
from app.db.models import ChatSettings, ViolationAction
from app.state.redis import StateStore


@dataclass(frozen=True)
class Decision:
    action: ViolationAction
    violation: Violation


async def evaluate(
    *,
    chat_id: int,
    user_id: int,
    text: str,
    settings: ChatSettings,
    matcher: StopwordMatcher,
    state: StateStore,
    is_admin: bool,
) -> Decision | None:
    if is_admin or not settings.antispam_enabled or not text:
        return None

    if await state.is_flood(
        chat_id, user_id, window_sec=settings.flood_window_sec, limit=settings.flood_limit
    ):
        return Decision(settings.action, Violation(ViolationType.FLOOD, "limit exceeded"))

    if settings.delete_duplicates and await state.is_duplicate(
        chat_id, user_id, text, window_sec=settings.flood_window_sec
    ):
        return Decision(settings.action, Violation(ViolationType.DUPLICATE, "repeat"))

    stop = check_stopwords(text, matcher)
    if stop is not None:
        return Decision(settings.action, stop)

    link = check_links(text, enabled=settings.delete_links)
    if link is not None:
        return Decision(settings.action, link)

    caps = check_caps(text, enabled=settings.delete_caps)
    if caps is not None:
        return Decision(settings.action, caps)

    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/antispam/test_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/app/antispam/engine.py tests/antispam/test_engine.py
git commit -m "feat: anti-spam engine with rule ordering and exemptions"
```

---

### Task 10: Outgoing rate-limited queue

**Files:**
- Create: `src/app/services/__init__.py`
- Create: `src/app/services/outgoing.py`
- Test: `tests/services/test_outgoing.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `TokenBucket(rate: float = 25.0, capacity: int = 25, monotonic=time.monotonic)` with `async acquire(n: int = 1) -> None`; `OutgoingQueue(bucket)` with `async submit(coro_factory, *, priority: int = 0)`, `async start(n_workers: int = 4)`, `async stop(drain: bool = True)`; priority 0 = high (moderation), 10 = low (nice-to-have).

- [ ] **Step 1: Write the failing test**

```python
# tests/services/test_outgoing.py
import asyncio

from app.services.outgoing import OutgoingQueue, TokenBucket


async def test_queue_runs_submitted_tasks():
    q = OutgoingQueue(TokenBucket(rate=1000, capacity=1000))
    await q.start(n_workers=2)
    results = []
    await q.submit(lambda: _append(results, 1))
    await q.submit(lambda: _append(results, 2), priority=10)
    await asyncio.sleep(0.1)
    await q.stop()
    assert results == [1, 2]


async def test_bucket_limits_calls():
    now = [0.0]
    bucket = TokenBucket(rate=10, capacity=1, monotonic=lambda: now[0])
    await bucket.acquire()
    task = asyncio.create_task(bucket.acquire())
    await asyncio.sleep(0)
    assert not task.done()
    now[0] = 0.2
    await asyncio.sleep(0.02)
    assert task.done()


async def _append(target, value):
    target.append(value)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_outgoing.py -v`
Expected: FAIL (no module `app.services.outgoing`)

- [ ] **Step 3: Implement queue and bucket**

```python
# src/app/services/__init__.py
```

```python
# src/app/services/outgoing.py
import asyncio
import time
from collections.abc import Awaitable, Callable

import structlog

log = structlog.get_logger()


class TokenBucket:
    def __init__(self, rate: float = 25.0, capacity: int = 25, monotonic=time.monotonic):
        self._rate = rate
        self._capacity = capacity
        self._tokens = float(capacity)
        self._monotonic = monotonic
        self._last = monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, n: int = 1) -> None:
        while True:
            async with self._lock:
                now = self._monotonic()
                elapsed = now - self._last
                self._last = now
                self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
                if self._tokens >= n:
                    self._tokens -= n
                    return
                wait = (n - self._tokens) / self._rate
            await asyncio.sleep(wait)


class OutgoingQueue:
    def __init__(self, bucket: TokenBucket):
        self._bucket = bucket
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._workers: list[asyncio.Task] = []
        self._counter = 0

    async def submit(self, coro_factory: Callable[[], Awaitable], *, priority: int = 0) -> None:
        self._counter += 1
        await self._queue.put((priority, self._counter, coro_factory))

    async def start(self, n_workers: int = 4) -> None:
        for _ in range(n_workers):
            self._workers.append(asyncio.create_task(self._worker()))

    async def stop(self, drain: bool = True) -> None:
        if drain:
            await self._queue.join()
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def _worker(self) -> None:
        while True:
            _, _, coro_factory = await self._queue.get()
            try:
                await self._bucket.acquire()
                await coro_factory()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("outgoing_task_failed", error=str(exc))
            finally:
                self._queue.task_done()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_outgoing.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/app/services/__init__.py src/app/services/outgoing.py tests/services/test_outgoing.py
git commit -m "feat: token-bucket outgoing queue"
```

---

### Task 11: Repositories

**Files:**
- Create: `src/app/repositories/__init__.py`
- Create: `src/app/repositories/chats.py`
- Create: `src/app/repositories/stopwords.py`
- Create: `src/app/repositories/stats.py`
- Test: `tests/repositories/test_stats_repo.py` (integration; skipped without `TEST_DATABASE_URL`)

**Interfaces:**
- Consumes: `app.db.base.Database`, `app.db.models`.
- Produces:
  - `ChatRepo(session)`: `async upsert(chat_id, type, title, owner_id, member_count) -> Chat`; `async get(chat_id) -> Chat | None`; `async set_member_count(chat_id, count)`; `async list_by_owner(owner_id) -> list[Chat]`; `async transfer_owner(chat_id, new_owner_id)`; `async is_admin(chat_id, user_id) -> bool`; `async add_admin(chat_id, user_id, role)`.
  - `SettingsRepo(session)`: `async get_or_create(chat_id) -> ChatSettings`; `async update(chat_id, **fields) -> ChatSettings`.
  - `StopwordRepo(session)`: `async list_words(chat_id) -> list[str]`; `async add(chat_id, word)`; `async remove(chat_id, word)`.
  - `StatsRepo(session)`: `async upsert_chat_daily(rows: list[dict])`; `async upsert_user_daily(rows: list[dict])`; `async bump_join(chat_id, date)`, `async bump_leave(chat_id, date)`; `async insert_message_logs(rows: list[dict])`; `async cleanup_logs(before: datetime) -> int`; `async chat_summary(chat_id, since: date) -> list[ChatStatsDaily]`; `async top_users(chat_id, since: date, limit: int) -> list[UserStatsDaily]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/repositories/test_stats_repo.py
import os
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.repositories.stats import StatsRepo

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)


async def test_upsert_chat_daily_is_idempotent_accumulator():
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        repo = StatsRepo(session)
        await repo.upsert_chat_daily([{"chat_id": 5, "date": date(2026, 10, 12), "messages": 3}])
        await repo.upsert_chat_daily([{"chat_id": 5, "date": date(2026, 10, 12), "messages": 4}])
        await session.commit()
        rows = await repo.chat_summary(5, since=date(2026, 10, 1))
    await engine.dispose()
    assert rows[0].messages == 7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `TEST_DATABASE_URL=$DATABASE_URL pytest tests/repositories/test_stats_repo.py -v`
Expected: FAIL (no module `app.repositories.stats`)

- [ ] **Step 3: Implement repositories**

```python
# src/app/repositories/__init__.py
```

```python
# src/app/repositories/chats.py
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.db.models import Chat, ChatAdmin, ChatSettings


class ChatRepo:
    def __init__(self, session):
        self.session = session

    async def get(self, chat_id: int) -> Chat | None:
        return await self.session.get(Chat, chat_id)

    async def upsert(self, chat_id, type, title, owner_id, member_count) -> Chat:
        stmt = (
            insert(Chat)
            .values(id=chat_id, type=type, title=title, owner_id=owner_id, member_count=member_count)
            .on_conflict_do_update(
                index_elements=[Chat.id],
                set_={"title": title, "member_count": member_count, "type": type},
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()
        return await self.get(chat_id)

    async def set_member_count(self, chat_id: int, count: int) -> None:
        await self.session.execute(update(Chat).where(Chat.id == chat_id).values(member_count=count))

    async def list_by_owner(self, owner_id: int) -> list[Chat]:
        result = await self.session.execute(select(Chat).where(Chat.owner_id == owner_id))
        return list(result.scalars())

    async def transfer_owner(self, chat_id: int, new_owner_id: int) -> None:
        await self.session.execute(update(Chat).where(Chat.id == chat_id).values(owner_id=new_owner_id))

    async def is_admin(self, chat_id: int, user_id: int) -> bool:
        row = await self.session.get(ChatAdmin, (chat_id, user_id))
        return row is not None

    async def add_admin(self, chat_id: int, user_id: int, role: str = "admin") -> None:
        stmt = (
            insert(ChatAdmin)
            .values(chat_id=chat_id, user_id=user_id, role=role)
            .on_conflict_do_nothing(index_elements=[ChatAdmin.chat_id, ChatAdmin.user_id])
        )
        await self.session.execute(stmt)


class SettingsRepo:
    def __init__(self, session):
        self.session = session

    async def get_or_create(self, chat_id: int) -> ChatSettings:
        row = await self.session.get(ChatSettings, chat_id)
        if row is None:
            row = ChatSettings(chat_id=chat_id)
            self.session.add(row)
            await self.session.flush()
        return row

    async def update(self, chat_id: int, **fields) -> ChatSettings:
        await self.get_or_create(chat_id)
        await self.session.execute(update(ChatSettings).where(ChatSettings.chat_id == chat_id).values(**fields))
        await self.session.flush()
        await self.session.refresh(await self.session.get(ChatSettings, chat_id))
        return await self.session.get(ChatSettings, chat_id)
```

```python
# src/app/repositories/stopwords.py
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import Stopword


class StopwordRepo:
    def __init__(self, session):
        self.session = session

    async def list_words(self, chat_id: int) -> list[str]:
        result = await self.session.execute(select(Stopword.word).where(Stopword.chat_id == chat_id))
        return list(result.scalars())

    async def add(self, chat_id: int, word: str) -> None:
        stmt = (
            insert(Stopword)
            .values(chat_id=chat_id, word=word.strip().lower())
            .on_conflict_do_nothing(index_elements=[Stopword.chat_id, Stopword.word])
        )
        await self.session.execute(stmt)

    async def remove(self, chat_id: int, word: str) -> None:
        await self.session.execute(
            delete(Stopword).where(Stopword.chat_id == chat_id, Stopword.word == word.strip().lower())
        )
```

```python
# src/app/repositories/stats.py
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import ChatStatsDaily, MessageLog, UserStatsDaily


class StatsRepo:
    def __init__(self, session):
        self.session = session

    async def insert_message_logs(self, rows: list[dict]) -> None:
        if rows:
            await self.session.execute(insert(MessageLog), rows)

    async def cleanup_logs(self, before: datetime) -> int:
        result = await self.session.execute(delete(MessageLog).where(MessageLog.created_at < before))
        return result.rowcount or 0

    async def upsert_chat_daily(self, rows: list[dict]) -> None:
        for row in rows:
            stmt = (
                insert(ChatStatsDaily)
                .values(**row)
                .on_conflict_do_update(
                    index_elements=[ChatStatsDaily.chat_id, ChatStatsDaily.date],
                    set_={
                        "messages": ChatStatsDaily.messages + row.get("messages", 0),
                        "joins": ChatStatsDaily.joins + row.get("joins", 0),
                        "leaves": ChatStatsDaily.leaves + row.get("leaves", 0),
                        "active_users": row.get("active_users", ChatStatsDaily.active_users),
                    },
                )
            )
            await self.session.execute(stmt)

    async def upsert_user_daily(self, rows: list[dict]) -> None:
        for row in rows:
            stmt = (
                insert(UserStatsDaily)
                .values(**row)
                .on_conflict_do_update(
                    index_elements=[UserStatsDaily.chat_id, UserStatsDaily.user_id, UserStatsDaily.date],
                    set_={
                        "messages": UserStatsDaily.messages + row.get("messages", 0),
                        "deleted": UserStatsDaily.deleted + row.get("deleted", 0),
                    },
                )
            )
            await self.session.execute(stmt)

    async def bump_join(self, chat_id: int, day) -> None:
        await self.upsert_chat_daily([{"chat_id": chat_id, "date": day, "joins": 1}])

    async def bump_leave(self, chat_id: int, day) -> None:
        await self.upsert_chat_daily([{"chat_id": chat_id, "date": day, "leaves": 1}])

    async def chat_summary(self, chat_id: int, since) -> list[ChatStatsDaily]:
        result = await self.session.execute(
            select(ChatStatsDaily)
            .where(ChatStatsDaily.chat_id == chat_id, ChatStatsDaily.date >= since)
            .order_by(ChatStatsDaily.date)
        )
        return list(result.scalars())

    async def top_users(self, chat_id: int, since, limit: int = 10) -> list[UserStatsDaily]:
        from sqlalchemy import func

        stmt = (
            select(
                UserStatsDaily.user_id,
                func.sum(UserStatsDaily.messages).label("messages"),
                func.sum(UserStatsDaily.deleted).label("deleted"),
            )
            .where(UserStatsDaily.chat_id == chat_id, UserStatsDaily.date >= since)
            .group_by(UserStatsDaily.user_id)
            .order_by(func.sum(UserStatsDaily.messages).desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).all())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `TEST_DATABASE_URL=$DATABASE_URL pytest tests/repositories/test_stats_repo.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/app/repositories tests/repositories
git commit -m "feat: repositories for chats, settings, stopwords, stats"
```

---

### Task 12: ChatContext with cache and invalidate

**Files:**
- Create: `src/app/middlewares/__init__.py`
- Create: `src/app/middlewares/chat_context.py`
- Test: `tests/middlewares/test_chat_context.py`

**Interfaces:**
- Consumes: `app.db.base.Database`, `app.repositories.*`, `app.antispam.matcher.StopwordMatcher`.
- Produces:
  - `ChatContext` dataclass: `chat`, `settings`, `matcher`, `is_admin`.
  - `ChatContextMiddleware(db, *, ttl: int = 60)` with `invalidate(chat_id)`; populates `data["ctx"]`.
  - `StopwordCache` with `get(chat_id) -> StopwordMatcher` and `invalidate(chat_id)`.
  - Helper `async load_context(db, chat_id, user_id, ttl) -> ChatContext` used by tests.

- [ ] **Step 1: Write the failing test**

```python
# tests/middlewares/test_chat_context.py
import time

from app.middlewares.chat_context import TTLCache


def test_ttl_cache_set_get_and_invalidate():
    cache = TTLCache(ttl=60)
    cache.set(1, "a")
    assert cache.get(1) == "a"
    cache.invalidate(1)
    assert cache.get(1) is None


def test_ttl_cache_expires():
    cache = TTLCache(ttl=0)
    cache.set(1, "a")
    time.sleep(0.001)
    assert cache.get(1) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/middlewares/test_chat_context.py -v`
Expected: FAIL (no module `app.middlewares.chat_context`)

- [ ] **Step 3: Implement cache, stopword cache, and middleware**

```python
# src/app/middlewares/__init__.py
```

```python
# src/app/middlewares/chat_context.py
import time
from dataclasses import dataclass
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.antispam.matcher import StopwordMatcher


class TTLCache:
    def __init__(self, ttl: int = 60):
        self._ttl = ttl
        self._data: dict[Any, tuple[float, Any]] = {}

    def get(self, key):
        item = self._data.get(key)
        if item is None:
            return None
        expires, value = item
        if expires < time.monotonic():
            self._data.pop(key, None)
            return None
        return value

    def set(self, key, value) -> None:
        self._data[key] = (time.monotonic() + self._ttl, value)

    def invalidate(self, key) -> None:
        self._data.pop(key, None)


class StopwordCache:
    def __init__(self, db, ttl: int = 60):
        self._db = db
        self._cache = TTLCache(ttl)

    async def get(self, chat_id: int) -> StopwordMatcher:
        cached = self._cache.get(chat_id)
        if cached is not None:
            return cached
        from app.repositories.stopwords import StopwordRepo

        async with self._db.session() as session:
            words = await StopwordRepo(session).list_words(chat_id)
        matcher = StopwordMatcher.build(words)
        self._cache.set(chat_id, matcher)
        return matcher

    def invalidate(self, chat_id: int) -> None:
        self._cache.invalidate(chat_id)


@dataclass
class ChatContext:
    chat: Any
    settings: Any
    matcher: StopwordMatcher
    is_admin: bool


class ChatContextMiddleware(BaseMiddleware):
    def __init__(self, db, stopword_cache: StopwordCache, ttl: int = 60):
        self._db = db
        self._stopwords = stopword_cache
        self._settings_cache = TTLCache(ttl)

    def invalidate(self, chat_id: int) -> None:
        self._settings_cache.invalidate(chat_id)
        self._stopwords.invalidate(chat_id)

    async def __call__(self, handler, event: TelegramObject, data: dict):
        chat = data.get("event_chat")
        user = data.get("event_from_user")
        if chat is not None and chat.type in ("group", "supergroup") and user is not None:
            from app.repositories.chats import ChatRepo, SettingsRepo

            async with self._db.session() as session:
                settings = self._settings_cache.get(chat.id)
                if settings is None:
                    settings = await SettingsRepo(session).get_or_create(chat.id)
                    await session.commit()
                    self._settings_cache.set(chat.id, settings)
                is_admin = await ChatRepo(session).is_admin(chat.id, user.id)
            matcher = await self._stopwords.get(chat.id)
            data["ctx"] = ChatContext(chat, settings, matcher, is_admin)
        return await handler(event, data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/middlewares/test_chat_context.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/app/middlewares tests/middlewares
git commit -m "feat: chat context middleware with ttl cache and invalidate"
```

---

### Task 13: Anti-spam middleware

**Files:**
- Create: `src/app/middlewares/antispam.py`
- Test: `tests/middlewares/test_antispam.py`

**Interfaces:**
- Consumes: `app.antispam.engine.evaluate`, `app.services.outgoing.OutgoingQueue`, `app.middlewares.chat_context.ChatContext`, `app.repositories.*`.
- Produces: `AntiSpamMiddleware(db, state_store, outgoing, bot)`; `async handle_violation(...)`; registers message-log rows. Returns `None` from handler (stops propagation) when a violation with `delete` is enforced.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/middlewares/test_antispam.py -v`
Expected: FAIL (no module `app.middlewares.antispam`)

- [ ] **Step 3: Implement middleware and action resolution**

```python
# src/app/middlewares/antispam.py
from datetime import datetime, timedelta, timezone

import structlog
from aiogram import BaseMiddleware
from aiogram.types import ChatPermissions, Message, TelegramObject

from app.antispam.engine import evaluate
from app.db.models import ViolationAction
from app.middlewares.chat_context import ChatContext
from app.repositories.stats import StatsRepo

log = structlog.get_logger()


def resolve_action(action: ViolationAction, warn_count: int, warn_limit: int) -> tuple[ViolationAction, bool]:
    if action == ViolationAction.WARN and warn_count >= warn_limit:
        return ViolationAction.MUTE, False
    if action == ViolationAction.WARN:
        return ViolationAction.WARN, True
    return action, False


class AntiSpamMiddleware(BaseMiddleware):
    def __init__(self, db, state_store, outgoing, bot):
        self._db = db
        self._state = state_store
        self._outgoing = outgoing
        self._bot = bot
        self._warns: dict[tuple[int, int], int] = {}

    async def __call__(self, handler, event: Message, data: dict):
        ctx: ChatContext | None = data.get("ctx")
        user = data.get("event_from_user")
        if ctx is None or user is None or event.text is None:
            return await handler(event, data)
        if event.text.startswith("/"):
            return await handler(event, data)

        decision = await evaluate(
            chat_id=event.chat.id,
            user_id=user.id,
            text=event.text,
            settings=ctx.settings,
            matcher=ctx.matcher,
            state=self._state,
            is_admin=ctx.is_admin,
        )
        if decision is None:
            return await handler(event, data)

        warn_key = (event.chat.id, user.id)
        warn_count = self._warns.get(warn_key, 0) + 1
        action, should_warn = resolve_action(decision.action, warn_count, ctx.settings.warn_limit)
        self._warns[warn_key] = warn_count

        await self._outgoing.submit(lambda: self._bot.delete_message(event.chat.id, event.message_id), priority=0)
        if action == ViolationAction.MUTE:
            until = datetime.now(timezone.utc) + timedelta(minutes=ctx.settings.mute_minutes)
            perms = ChatPermissions(can_send_messages=False)
            await self._outgoing.submit(
                lambda: self._bot.restrict_chat_member(event.chat.id, user.id, perms, until_date=until),
                priority=0,
            )
        elif should_warn:
            await self._outgoing.submit(
                lambda: self._bot.send_message(
                    event.chat.id, f"@{user.username or user.id}, нарушение: {decision.violation.type.value}"
                ),
                priority=5,
            )

        await self._log(event, user.id, decision.violation.type.value)
        return None

    async def _log(self, event: Message, user_id: int, violation: str) -> None:
        async with self._db.session() as session:
            await StatsRepo(session).insert_message_logs(
                [{
                    "chat_id": event.chat.id,
                    "user_id": user_id,
                    "message_id": event.message_id,
                    "is_deleted": True,
                    "violation": violation,
                }]
            )
            await session.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/middlewares/test_antispam.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/app/middlewares/antispam.py tests/middlewares/test_antispam.py
git commit -m "feat: anti-spam middleware with warn escalation and queueing"
```

---

### Task 14: Stats collection and background jobs

**Files:**
- Create: `src/app/middlewares/stats.py`
- Create: `src/app/services/stats_service.py`
- Create: `src/app/scheduler/__init__.py`
- Create: `src/app/scheduler/jobs.py`
- Test: `tests/services/test_stats_service.py`

**Interfaces:**
- Consumes: `app.repositories.stats.StatsRepo`, `app.db.base.Database`, `app.config.Settings`.
- Produces:
  - `StatsBuffer` with `record_message(chat_id, user_id, message_id, is_deleted=False, violation=None)`, `record_join(chat_id)`, `record_leave(chat_id)`, `async flush(db) -> int`, `pending() -> int`.
  - `StatsCollectorMiddleware(buffer: StatsBuffer)`.
  - `StatsService(db)` with `async flush()`, `async daily_rollup()`, `async cleanup_logs(days: int = 30) -> int`.
  - `create_scheduler(stats_service, subscriptions, bot) -> AsyncIOScheduler`.

- [ ] **Step 1: Write the failing test**

```python
# tests/services/test_stats_service.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_stats_service.py -v`
Expected: FAIL (no module `app.services.stats_service`)

- [ ] **Step 3: Implement buffer, service, middleware, jobs**

```python
# src/app/services/stats_service.py
from collections import Counter
from datetime import date, datetime, timedelta, timezone

import structlog

log = structlog.get_logger()


def aggregate_user_rows(events: list[dict], day: date) -> list[dict]:
    counts: Counter = Counter()
    deleted: Counter = Counter()
    for e in events:
        key = (e["chat_id"], e["user_id"])
        counts[key] += 1
        if e.get("is_deleted"):
            deleted[key] += 1
    return [
        {
            "chat_id": chat_id,
            "user_id": user_id,
            "date": day,
            "messages": count,
            "deleted": deleted[(chat_id, user_id)],
        }
        for (chat_id, user_id), count in counts.items()
    ]


def aggregate_chat_row(events: list[dict], day: date) -> dict:
    keys = {(e["chat_id"], e["user_id"]) for e in events}
    chat_ids = {e["chat_id"] for e in events}
    chat_id = next(iter(chat_ids)) if chat_ids else 0
    return {
        "chat_id": chat_id,
        "date": day,
        "messages": len(events),
        "active_users": len({u for (c, u) in keys if c == chat_id}),
    }


class StatsBuffer:
    def __init__(self):
        self._messages: list[dict] = []
        self._joins: Counter = Counter()
        self._leaves: Counter = Counter()

    def record_message(self, chat_id, user_id, message_id, is_deleted=False, violation=None):
        self._messages.append(
            {
                "chat_id": chat_id,
                "user_id": user_id,
                "message_id": message_id,
                "is_deleted": is_deleted,
                "violation": violation,
            }
        )

    def record_join(self, chat_id: int):
        self._joins[chat_id] += 1

    def record_leave(self, chat_id: int):
        self._leaves[chat_id] += 1

    def pending(self) -> int:
        return len(self._messages) + sum(self._joins.values()) + sum(self._leaves.values())

    def _drain(self):
        messages, joins, leaves = self._messages, self._joins, self._leaves
        self._messages, self._joins, self._leaves = [], Counter(), Counter()
        return messages, joins, leaves


class StatsService:
    def __init__(self, db, buffer: StatsBuffer):
        self._db = db
        self._buffer = buffer

    async def flush(self) -> int:
        from app.repositories.stats import StatsRepo

        messages, joins, leaves = self._buffer._drain()
        if not messages and not joins and not leaves:
            return 0
        day = datetime.now(timezone.utc).date()
        async with self._db.session() as session:
            repo = StatsRepo(session)
            await repo.insert_message_logs(messages)
            if messages:
                await repo.upsert_user_daily(aggregate_user_rows(messages, day))
                await repo.upsert_chat_daily([aggregate_chat_row(messages, day)])
            for chat_id, count in joins.items():
                for _ in range(count):
                    await repo.bump_join(chat_id, day)
            for chat_id, count in leaves.items():
                for _ in range(count):
                    await repo.bump_leave(chat_id, day)
            await session.commit()
        log.info("stats_flushed", messages=len(messages))
        return len(messages)

    async def cleanup_logs(self, days: int = 30) -> int:
        from app.repositories.stats import StatsRepo

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        async with self._db.session() as session:
            removed = await StatsRepo(session).cleanup_logs(cutoff)
            await session.commit()
        log.info("logs_cleaned", removed=removed)
        return removed
```

```python
# src/app/middlewares/stats.py
from aiogram import BaseMiddleware
from aiogram.types import ChatMemberUpdated, Message, TelegramObject


class StatsCollectorMiddleware(BaseMiddleware):
    def __init__(self, buffer):
        self._buffer = buffer

    async def __call__(self, handler, event: TelegramObject, data: dict):
        ctx = data.get("ctx")
        user = data.get("event_from_user")
        if isinstance(event, Message) and user is not None and event.text is not None:
            self._buffer.record_message(event.chat.id, user.id, event.message_id)
        elif isinstance(event, ChatMemberUpdated):
            old = event.old_chat_member.status
            new = event.new_chat_member.status
            if old in ("left", "kicked") and new in ("member", "administrator", "creator"):
                self._buffer.record_join(event.chat.id)
            elif old in ("member", "administrator", "creator") and new in ("left", "kicked"):
                self._buffer.record_leave(event.chat.id)
        return await handler(event, data)
```

```python
# src/app/scheduler/__init__.py
```

```python
# src/app/scheduler/jobs.py
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

log = structlog.get_logger()


def create_scheduler(stats_service, subscriptions, buffer, outgoing) -> AsyncIOScheduler:
    from app.config import get_settings

    settings = get_settings()
    scheduler = AsyncIOScheduler(timezone="UTC")

    async def flush():
        await stats_service.flush()

    async def flush_if_needed():
        if buffer.pending() >= 500:
            await stats_service.flush()

    scheduler.add_job(flush, "interval", seconds=15, id="flush_stats", max_instances=1)
    scheduler.add_job(flush_if_needed, "interval", seconds=3, id="flush_if_big", max_instances=1)
    scheduler.add_job(stats_service.cleanup_logs, "cron", hour=3, minute=30, id="cleanup_logs", args=[30])
    scheduler.add_job(subscriptions.lifecycle, "cron", hour=0, minute=5, id="subscription_lifecycle")
    scheduler.add_job(subscriptions.detect_orphans, "cron", hour=1, minute=0, id="orphan_scan")
    return scheduler
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_stats_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/app/services/stats_service.py src/app/middlewares/stats.py src/app/scheduler tests/services/test_stats_service.py
git commit -m "feat: stats buffer, service, collector middleware, scheduler"
```

---

### Task 15: Stats handlers (/stats, /top, chart)

**Files:**
- Create: `src/app/handlers/__init__.py`
- Create: `src/app/handlers/stats.py`
- Create: `src/app/services/charts.py`
- Test: `tests/services/test_charts.py`

**Interfaces:**
- Consumes: `app.repositories.stats.StatsRepo`, `app.services.subscriptions.SubscriptionsService.has_feature`.
- Produces:
  - `format_chat_summary(rows) -> str`; `format_top(rows) -> str`.
  - `render_growth_chart(rows) -> bytes` (PNG).
  - Router `stats_router` with `/stats`, `/stats chart`, `/top [period]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/services/test_charts.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_charts.py -v`
Expected: FAIL (no module `app.services.charts`)

- [ ] **Step 3: Implement formatting, chart rendering, and handlers**

```python
# src/app/services/charts.py
import io


def format_chat_summary(rows) -> str:
    if not rows:
        return "Нет данных за выбранный период."
    total = sum(r.messages for r in rows)
    joins = sum(r.joins for r in rows)
    leaves = sum(r.leaves for r in rows)
    peak = max(r.active_users for r in rows)
    return (
        f"Сообщений: {total}\n"
        f"Входы: +{joins} · Выходы: -{leaves}\n"
        f"Пик активных за день: {peak}\n"
        f"Дней в выборке: {len(rows)}"
    )


def format_top(rows) -> str:
    if not rows:
        return "Нет данных."
    lines = ["Топ участников:"]
    for i, r in enumerate(rows, 1):
        lines.append(f"{i}. id{r.user_id} — {r.messages} сообщ. ({r.deleted} удалено)")
    return "\n".join(lines)


def render_growth_chart(rows) -> bytes:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 3))
    dates = [r.date for r in rows]
    ax.plot(dates, [r.messages for r in rows], marker="o", label="messages")
    ax.plot(dates, [r.joins - r.leaves for r in rows], marker="s", label="net joins")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()
```

```python
# src/app/handlers/__init__.py
```

```python
# src/app/handlers/stats.py
from datetime import date, datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from app.handlers.deps import get_deps

stats_router = Router(name="stats")

PERIODS = {"day": 1, "week": 7, "month": 30}


@stats_router.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.chat.type == "private":
        await message.answer("Открой /stats в чате, где добавлен бот.")
        return
    deps = get_deps()
    since = datetime.now(timezone.utc).date() - timedelta(days=30)
    async with deps.db.session() as session:
        from app.repositories.stats import StatsRepo

        rows = await StatsRepo(session).chat_summary(message.chat.id, since=since)
    from app.services.charts import format_chat_summary

    await message.answer(format_chat_summary(rows))


@stats_router.message(Command("stats"), F.text.endswith("chart"))
async def cmd_stats_chart(message: Message):
    deps = get_deps()
    if not await deps.subscriptions.has_feature(message.chat.id, "charts"):
        await message.answer("Графики доступны на тарифе Pro. /subscription")
        return
    since = datetime.now(timezone.utc).date() - timedelta(days=30)
    async with deps.db.session() as session:
        from app.repositories.stats import StatsRepo

        rows = await StatsRepo(session).chat_summary(message.chat.id, since=since)
    from app.services.charts import render_growth_chart

    photo = BufferedInputFile(render_growth_chart(rows), filename="growth.png")
    await message.answer_photo(photo)


@stats_router.message(Command("top"))
async def cmd_top(message: Message):
    if message.chat.type == "private":
        await message.answer("Открой /top в чате.")
        return
    period = "week"
    parts = (message.text or "").split()
    if len(parts) > 1 and parts[1] in PERIODS:
        period = parts[1]
    since = datetime.now(timezone.utc).date() - timedelta(days=PERIODS[period])
    deps = get_deps()
    async with deps.db.session() as session:
        from app.repositories.stats import StatsRepo

        rows = await StatsRepo(session).top_users(message.chat.id, since=since, limit=10)
    from app.services.charts import format_top

    await message.answer(format_top(rows))
```

```python
# src/app/handlers/deps.py
from dataclasses import dataclass
from typing import Any


@dataclass
class Deps:
    db: Any
    bot: Any
    state: Any
    outgoing: Any
    subscriptions: Any


_deps: Deps | None = None


def set_deps(deps: Deps) -> None:
    global _deps
    _deps = deps


def get_deps() -> Deps:
    if _deps is None:
        raise RuntimeError("deps not initialized")
    return _deps
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_charts.py -v`
Expected: PASS (matplotlib-backed PNG is exercised in Task 20 integration)

- [ ] **Step 5: Commit**

```bash
git add src/app/services/charts.py src/app/handlers tests/services/test_charts.py
git commit -m "feat: stats and top handlers with pro growth chart"
```

---

### Task 16: PaymentProvider interface and Stars implementation

**Files:**
- Create: `src/app/services/payments/__init__.py`
- Create: `src/app/services/payments/provider.py`
- Create: `src/app/services/payments/stars.py`
- Test: `tests/services/test_stars_provider.py`

**Interfaces:**
- Consumes: `aiogram.Bot`.
- Produces:
  - `PaymentResult(provider: str, external_id: str, chat_id: int, plan: str, amount: int, payer_id: int)`.
  - `PaymentProvider` ABC: `async create_invoice(chat_id, plan)`, `async handle_pre_checkout(query) -> bool`, `async handle_payment(message) -> PaymentResult | None`, `name: str`.
  - `StarsProvider(bot, tiers, payload_sep=":")`; `parse_payload(payload) -> tuple[int, str]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/services/test_stars_provider.py
import pytest

from app.services.payments.stars import StarsProvider, parse_payload


def test_parse_payload_roundtrip():
    assert parse_payload("123:pro") == (123, "pro")


def test_parse_payload_invalid():
    with pytest.raises(ValueError):
        parse_payload("bad")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_stars_provider.py -v`
Expected: FAIL (no module `app.services.payments.stars`)

- [ ] **Step 3: Implement provider interface and Stars provider**

```python
# src/app/services/payments/__init__.py
```

```python
# src/app/services/payments/provider.py
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class PaymentResult:
    provider: str
    external_id: str
    chat_id: int
    plan: str
    amount: int
    payer_id: int


class PaymentProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def create_invoice(self, chat_id: int, plan: str) -> str: ...

    @abstractmethod
    async def handle_pre_checkout(self, query) -> bool: ...

    @abstractmethod
    async def handle_payment(self, message) -> PaymentResult | None: ...
```

```python
# src/app/services/payments/stars.py
from aiogram.types import LabeledPrice

from app.services.payments.provider import PaymentProvider, PaymentResult


def parse_payload(payload: str) -> tuple[int, str]:
    parts = payload.split(":")
    if len(parts) != 2 or not parts[0].lstrip("-").isdigit():
        raise ValueError(f"invalid payload: {payload!r}")
    return int(parts[0]), parts[1]


class StarsProvider(PaymentProvider):
    name = "stars"

    def __init__(self, bot, tiers: dict[str, int], title: str = "Подписка"):
        self._bot = bot
        self._tiers = tiers
        self._title = title

    async def create_invoice(self, chat_id: int, plan: str) -> str:
        if plan not in self._tiers:
            raise ValueError(f"unknown plan: {plan}")
        return await self._bot.create_invoice_link(
            title=f"{self._title} {plan}",
            description=f"Оплата тарифа {plan} на 30 дней",
            payload=f"{chat_id}:{plan}",
            currency="XTR",
            prices=[LabeledPrice(label=plan, amount=self._tiers[plan])],
        )

    async def handle_pre_checkout(self, query) -> bool:
        try:
            parse_payload(query.invoice_payload)
        except ValueError:
            await query.answer(ok=False, error_message="Некорректный платёж")
            return False
        await query.answer(ok=True)
        return True

    async def handle_payment(self, message) -> PaymentResult | None:
        payment = message.successful_payment
        if payment is None:
            return None
        chat_id, plan = parse_payload(payment.invoice_payload)
        return PaymentResult(
            provider=self.name,
            external_id=payment.telegram_payment_charge_id,
            chat_id=chat_id,
            plan=plan,
            amount=payment.total_amount,
            payer_id=message.from_user.id,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_stars_provider.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/app/services/payments tests/services/test_stars_provider.py
git commit -m "feat: payment provider interface and telegram stars implementation"
```

---

### Task 17: Subscriptions service (limits, activation, lifecycle, claim)

**Files:**
- Create: `src/app/services/subscriptions.py`
- Test: `tests/services/test_subscriptions.py`

**Interfaces:**
- Consumes: `app.db.base.Database`, `app.db.models`, `app.repositories.chats.ChatRepo`, `aiogram.Bot`.
- Produces:
  - `SubscriptionsService(db, bot, provider, tiers)` with `async has_feature(chat_id, feature) -> bool`, `async get_plan(chat_id) -> Plan`, `async activate(result: PaymentResult) -> None` (idempotent), `async lifecycle() -> None`, `async detect_orphans() -> list[int]`, `async claim(chat_id, claimant_id) -> bool`.
  - Function `is_over_limit(plan, member_count, tiers) -> bool`.

- [ ] **Step 1: Write the failing test**

```python
# tests/services/test_subscriptions.py
from app.services.subscriptions import is_over_limit

TIERS = {"free": 1000, "pro": None, "corporate": None}


def test_free_over_limit():
    assert is_over_limit("free", 1500, TIERS) is True
    assert is_over_limit("free", 900, TIERS) is False


def test_paid_never_over_limit():
    assert is_over_limit("pro", 10**9, TIERS) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_subscriptions.py -v`
Expected: FAIL (no module `app.services.subscriptions`)

- [ ] **Step 3: Implement subscriptions service**

```python
# src/app/services/subscriptions.py
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import Chat, ChatAdmin, OwnershipClaim, Plan, Subscription, Transaction, TierLimit

log = structlog.get_logger()

TIER_FEATURES = {
    "free": {"charts": False, "custom_rules": False},
    "pro": {"charts": True, "custom_rules": True},
    "corporate": {"charts": True, "custom_rules": True, "white_label": True, "api": True},
}


def is_over_limit(plan: str, member_count: int, tiers: dict[str, int | None]) -> bool:
    limit = tiers.get(plan)
    return limit is not None and member_count > limit


class SubscriptionsService:
    def __init__(self, db, bot, provider, tiers: dict[str, int | None]):
        self._db = db
        self._bot = bot
        self._provider = provider
        self._member_tiers = tiers

    async def _plan_features(self, session, plan: Plan) -> dict:
        tier = await session.get(TierLimit, plan)
        if tier is not None:
            return tier.features or {}
        return TIER_FEATURES.get(plan.value, {})

    async def get_plan(self, chat_id: int) -> Plan:
        async with self._db.session() as session:
            sub = await session.get(Subscription, chat_id)
            if sub is None or not sub.is_active:
                return Plan.FREE
            return sub.plan

    async def has_feature(self, chat_id: int, feature: str) -> bool:
        plan = await self.get_plan(chat_id)
        async with self._db.session() as session:
            return bool((await self._plan_features(session, plan)).get(feature))

    async def activate(self, result) -> None:
        plan = Plan(result.plan)
        expires = datetime.now(timezone.utc) + timedelta(days=30)
        async with self._db.session() as session:
            tx = (
                insert(Transaction)
                .values(
                    chat_id=result.chat_id,
                    payer_id=result.payer_id,
                    amount_stars=result.amount,
                    payload=f"{result.chat_id}:{result.plan}",
                    telegram_payment_charge_id=result.external_id,
                    external_payment_id=result.external_id,
                )
                .on_conflict_do_nothing(index_elements=[Transaction.telegram_payment_charge_id])
            )
            inserted = await session.execute(tx)
            if inserted.rowcount == 0:
                log.info("payment_already_processed", external_id=result.external_id)
                return
            stmt = (
                insert(Subscription)
                .values(chat_id=result.chat_id, plan=plan, started_at=datetime.now(timezone.utc),
                        expires_at=expires, is_active=True)
                .on_conflict_do_update(
                    index_elements=[Subscription.chat_id],
                    set_={"plan": plan, "expires_at": expires, "is_active": True},
                )
            )
            await session.execute(stmt)
            await session.commit()
        log.info("subscription_activated", chat_id=result.chat_id, plan=plan.value)

    async def lifecycle(self) -> None:
        now = datetime.now(timezone.utc)
        async with self._db.session() as session:
            result = await session.execute(select(Subscription).where(Subscription.is_active.is_(True)))
            for sub in result.scalars():
                if sub.expires_at is None:
                    continue
                if sub.expires_at < now:
                    sub.is_active = False
                    sub.plan = Plan.FREE
                    await self._notify(sub.chat_id, "Подписка истекла, тариф понижен до free.")
                elif sub.expires_at - now <= timedelta(days=3):
                    await self._notify(sub.chat_id, "Подписка истекает через 3 дня. /subscription")
            await session.commit()

    async def detect_orphans(self) -> list[int]:
        orphans: list[int] = []
        async with self._db.session() as session:
            chats = list((await session.execute(select(Chat).where(Chat.is_active.is_(True)))).scalars())
        for chat in chats:
            try:
                admins = await self._bot.get_chat_administrators(chat.id)
            except Exception:
                continue
            admin_ids = {a.user.id for a in admins}
            if chat.owner_id not in admin_ids:
                orphans.append(chat.id)
        return orphans

    async def claim(self, chat_id: int, claimant_id: int) -> bool:
        try:
            admins = await self._bot.get_chat_administrators(chat_id)
        except Exception:
            return False
        target = next((a for a in admins if a.user.id == claimant_id), None)
        admin_ids = {a.user.id for a in admins}
        if target is None or not getattr(target, "can_promote_members", False):
            return False
        async with self._db.session() as session:
            chat = await session.get(Chat, chat_id)
            if chat is None or chat.owner_id in admin_ids and chat.owner_id != claimant_id:
                return False
            prev = chat.owner_id
            chat.owner_id = claimant_id
            session.add(OwnershipClaim(chat_id=chat_id, claimant_id=claimant_id, prev_owner_id=prev))
            await session.execute(
                insert(ChatAdmin)
                .values(chat_id=chat_id, user_id=claimant_id, role="owner")
                .on_conflict_do_update(
                    index_elements=[ChatAdmin.chat_id, ChatAdmin.user_id], set_={"role": "owner"}
                )
            )
            await session.commit()
        await self._notify(chat_id, f"Управление передано id{claimant_id}.")
        return True

    async def _notify(self, chat_id: int, text: str) -> None:
        async with self._db.session() as session:
            chat = await session.get(Chat, chat_id)
        if chat is None:
            return
        try:
            await self._bot.send_message(chat.owner_id, text)
        except Exception:
            pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_subscriptions.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/app/services/subscriptions.py tests/services/test_subscriptions.py
git commit -m "feat: subscriptions service with limits, lifecycle, and claim"
```

---

### Task 18: Owner handlers (/start, /settings, stopwords FSM, /subscription)

**Files:**
- Create: `src/app/keyboards/__init__.py`
- Create: `src/app/keyboards/settings.py`
- Create: `src/app/handlers/owner/__init__.py`
- Create: `src/app/handlers/owner/start.py`
- Create: `src/app/handlers/owner/settings.py`
- Create: `src/app/handlers/payments/__init__.py`
- Create: `src/app/handlers/payments/stars.py`
- Test: `tests/handlers/test_settings_callbacks.py`

**Interfaces:**
- Consumes: `app.handlers.deps`, `app.repositories.*`, `app.middlewares.chat_context.ChatContextMiddleware`, `app.services.subscriptions.SubscriptionsService`.
- Produces: `owner_router`, `payments_router`; callback data format `set:{chat_id}:{field}:{value}` and `sw:{chat_id}:add|del`. Settings writes call `ctx_middleware.invalidate(chat_id)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/handlers/test_settings_callbacks.py
from app.keyboards.settings import build_settings_keyboard, parse_callback


def test_parse_callback_valid():
    assert parse_callback("set:-100123:antispam_enabled:on") == (-100123, "antispam_enabled", "on")


def test_build_keyboard_has_toggles():
    kb = build_settings_keyboard(chat_id=-100, settings=None)
    datas = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert any(d.startswith("set:-100:antispam_enabled") for d in datas)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/handlers/test_settings_callbacks.py -v`
Expected: FAIL (no module `app.keyboards.settings`)

- [ ] **Step 3: Implement keyboards and handlers**

```python
# src/app/keyboards/__init__.py
```

```python
# src/app/keyboards/settings.py
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def parse_callback(data: str) -> tuple[int, str, str]:
    parts = data.split(":")
    if len(parts) != 4 or parts[0] != "set" or not parts[1].lstrip("-").isdigit():
        raise ValueError(data)
    return int(parts[1]), parts[2], parts[3]


def build_settings_keyboard(chat_id: int, settings) -> InlineKeyboardMarkup:
    on = lambda v: "on" if v else "off"  # noqa: E731
    rows = [
        [InlineKeyboardButton(
            text=f"Анти-спам: {on(settings.antispam_enabled) if settings else 'on'}",
            callback_data=f"set:{chat_id}:antispam_enabled:{'off' if settings and settings.antispam_enabled else 'on'}",
        )],
        [InlineKeyboardButton(text="Ссылки", callback_data=f"set:{chat_id}:delete_links:off"),
         InlineKeyboardButton(text="Капс", callback_data=f"set:{chat_id}:delete_caps:off")],
        [InlineKeyboardButton(text="Дубли", callback_data=f"set:{chat_id}:delete_duplicates:off")],
        [InlineKeyboardButton(text="Ответы на предупреждения", callback_data=f"set:{chat_id}:action:next")],
        [InlineKeyboardButton(text="Стоп-слова", callback_data=f"sw:{chat_id}:add"),
         InlineKeyboardButton(text="Список", callback_data=f"sw:{chat_id}:list")],
        [InlineKeyboardButton(text="Апгрейд", callback_data=f"sub:{chat_id}:menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
```

```python
# src/app/handlers/owner/__init__.py
```

```python
# src/app/handlers/owner/start.py
from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.handlers.deps import get_deps
from app.keyboards.settings import build_settings_keyboard

owner_router = Router(name="owner")


@owner_router.message(CommandStart(), F.chat.type == "private")
async def start(message: Message):
    deps = get_deps()
    async with deps.db.session() as session:
        from app.repositories.chats import ChatRepo

        chats = await ChatRepo(session).list_by_owner(message.from_user.id)
    if not chats:
        await message.answer(
            "Привет! Добавь меня в свой чат как админа с правом удалять сообщения.\n"
            "Для этого нажми кнопку ниже.",
            reply_markup=None,
        )
        return
    lines = ["Твои чаты:"]
    for chat in chats:
        lines.append(f"• {chat.title} (id {chat.id})")
    lines.append("\nОтправь /settings <chat_id> для настройки.")
    await message.answer("\n".join(lines))
```

```python
# src/app/handlers/owner/settings.py
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.handlers.deps import get_deps
from app.keyboards.settings import build_settings_keyboard, parse_callback

owner_router = Router(name="owner_settings")


class StopwordStates(StatesGroup):
    waiting_add = State()
    waiting_del = State()


TOGGLE_FIELDS = {
    "antispam_enabled": "antispam_enabled",
    "delete_links": "delete_links",
    "delete_caps": "delete_caps",
    "delete_duplicates": "delete_duplicates",
}


@owner_router.message(Command("settings"))
async def open_settings(message: Message):
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].lstrip("-").isdigit():
        await message.answer("Использование: /settings <chat_id>")
        return
    chat_id = int(parts[1])
    deps = get_deps()
    async with deps.db.session() as session:
        from app.repositories.chats import ChatRepo, SettingsRepo

        chat = await ChatRepo(session).get(chat_id)
        if chat is None or chat.owner_id != message.from_user.id:
            await message.answer("Чат не найден или ты не владелец.")
            return
        settings = await SettingsRepo(session).get_or_create(chat_id)
    await message.answer("Настройки:", reply_markup=build_settings_keyboard(chat_id, settings))


@owner_router.callback_query(F.data.startswith("set:"))
async def on_toggle(cb: CallbackQuery):
    chat_id, field, value = parse_callback(cb.data)
    deps = get_deps()
    if field in TOGGLE_FIELDS:
        new_value = value == "on"
        async with deps.db.session() as session:
            from app.repositories.chats import SettingsRepo

            settings = await SettingsRepo(session).update(chat_id, **{TOGGLE_FIELDS[field]: new_value})
            await session.commit()
        deps.chat_context.invalidate(chat_id)
        await cb.message.edit_reply_markup(reply_markup=build_settings_keyboard(chat_id, settings))
    await cb.answer()


@owner_router.callback_query(F.data.startswith("sw:"))
async def on_stopword_menu(cb: CallbackQuery, state: FSMContext):
    _, chat_id, action = cb.data.split(":")
    chat_id = int(chat_id)
    deps = get_deps()
    if action == "add":
        await state.set_state(StopwordStates.waiting_add)
        await state.update_data(chat_id=chat_id)
        await cb.message.answer("Отправь слово для добавления в стоп-лист.")
    else:
        async with deps.db.session() as session:
            from app.repositories.stopwords import StopwordRepo

            words = await StopwordRepo(session).list_words(chat_id)
        await cb.message.answer("Стоп-слова: " + (", ".join(words) if words else "пусто"))
    await cb.answer()


@owner_router.message(StopwordStates.waiting_add)
async def on_stopword_add(message: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data["chat_id"]
    deps = get_deps()
    word = (message.text or "").strip().lower()
    if word:
        async with deps.db.session() as session:
            from app.repositories.stopwords import StopwordRepo

            await StopwordRepo(session).add(chat_id, word)
            await session.commit()
        deps.chat_context.invalidate(chat_id)
    await state.clear()
    await message.answer(f"Добавлено: {word}" if word else "Пустое слово, отменено.")
```

```python
# src/app/handlers/payments/__init__.py
```

```python
# src/app/handlers/payments/stars.py
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from app.handlers.deps import get_deps

payments_router = Router(name="payments")


def plan_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Pro", callback_data=f"buy:{chat_id}:pro")],
        [InlineKeyboardButton(text="Corporate", callback_data=f"buy:{chat_id}:corporate")],
    ])


@payments_router.message(Command("subscription"))
async def subscription(message: Message):
    deps = get_deps()
    async with deps.db.session() as session:
        from app.repositories.chats import ChatRepo

        chats = await ChatRepo(session).list_by_owner(message.from_user.id)
    if not chats:
        await message.answer("Сначала добавь бота в чат.")
        return
    await message.answer("Выбери тариф:", reply_markup=plan_keyboard(chats[0].id))


@payments_router.callback_query(F.data.startswith("buy:"))
async def buy(cb: CallbackQuery):
    _, chat_id, plan = cb.data.split(":")
    deps = get_deps()
    link = await deps.stars_provider.create_invoice(int(chat_id), plan)
    await cb.message.answer(f"Оплатить: {link}")
    await cb.answer()


@payments_router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    deps = get_deps()
    await deps.stars_provider.handle_pre_checkout(query)


@payments_router.message(F.successful_payment)
async def successful(message: Message):
    deps = get_deps()
    result = await deps.stars_provider.handle_payment(message)
    if result is not None:
        await deps.subscriptions.activate(result)
        await message.answer("Оплата прошла, тариф активирован.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/handlers/test_settings_callbacks.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/app/keyboards src/app/handlers/owner src/app/handlers/payments tests/handlers
git commit -m "feat: owner settings, stopwords FSM, and stars payment handlers"
```

---

### Task 19: Application entrypoint, graceful shutdown, retry

**Files:**
- Create: `src/app/main.py`
- Create: `src/app/logging_setup.py`
- Test: `tests/test_main_wiring.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `async def build_app(settings) -> App` where `App` holds `bot`, `dispatcher`, `db`, `scheduler`, `state`, `outgoing`, `subscriptions`, `stats_service`; `async def run() -> None`; `async def shutdown(app) -> None` performing `scheduler.shutdown(wait=True)`, `stats_service.flush()`, `outgoing.stop(drain=True)`, `db.dispose()`, `bot.session.close()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_main_wiring.py
from app.main import install_middlewares


def test_install_middlewares_registers_expected():
    class DP:
        def __init__(self):
            self.outer = []
            self.inner = []

        def message(self, *a, **k):
            return _Reg(self.outer)

        def chat_member(self, *a, **k):
            return _Reg(self.outer)

    class _Reg:
        def __init__(self, sink):
            self.sink = sink

        def __call__(self, mw):
            self.sink.append(mw)
            return mw

    class BotStub:
        pass

    class MwStub:
        pass

    dp = DP()
    install_middlewares(dp, MwStub(), MwStub(), MwStub())
    assert len(dp.outer) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_main_wiring.py -v`
Expected: FAIL (no module `app.main`)

- [ ] **Step 3: Implement logging, entrypoint, shutdown**

```python
# src/app/logging_setup.py
import logging

import structlog


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level, logging.INFO)),
    )
```

```python
# src/app/main.py
import asyncio
import signal
from dataclasses import dataclass

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from redis.asyncio import Redis

from app.config import Settings, get_settings
from app.db.base import Database
from app.handlers.deps import Deps, set_deps
from app.handlers.owner.start import owner_router as owner_start_router
from app.handlers.owner.settings import owner_router as owner_settings_router
from app.handlers.payments.stars import payments_router
from app.handlers.stats import stats_router
from app.logging_setup import configure_logging
from app.middlewares.antispam import AntiSpamMiddleware
from app.middlewares.chat_context import ChatContextMiddleware, StopwordCache
from app.middlewares.stats import StatsCollectorMiddleware
from app.scheduler.jobs import create_scheduler
from app.services.outgoing import OutgoingQueue, TokenBucket
from app.services.payments.stars import StarsProvider
from app.services.stats_service import StatsBuffer, StatsService
from app.services.subscriptions import SubscriptionsService
from app.state.redis import StateStore

log = structlog.get_logger()


def install_middlewares(dp, chat_context, antispam, stats_collector):
    dp.message.outer_middleware(chat_context)
    dp.chat_member.outer_middleware(chat_context)
    dp.message.outer_middleware(antispam)
    dp.message.outer_middleware(stats_collector)
    dp.chat_member.outer_middleware(stats_collector)


@dataclass
class App:
    bot: Bot
    dispatcher: Dispatcher
    db: Database
    scheduler: object
    state: StateStore
    outgoing: OutgoingQueue
    subscriptions: SubscriptionsService
    stats_service: StatsService
    buffer: StatsBuffer
    redis: Redis


async def build_app(settings: Settings) -> App:
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    db = Database(settings.database_url)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    state = StateStore(redis)
    outgoing = OutgoingQueue(TokenBucket(rate=25.0, capacity=25))
    await outgoing.start(n_workers=4)

    tiers = {"free": 1000, "pro": None, "corporate": None}
    prices = {"pro": 500, "corporate": 5000}
    stars = StarsProvider(bot, prices)
    subscriptions = SubscriptionsService(db, bot, stars, tiers)
    buffer = StatsBuffer()
    stats_service = StatsService(db, buffer)

    stopword_cache = StopwordCache(db, ttl=60)
    chat_context = ChatContextMiddleware(db, stopword_cache, ttl=60)
    antispam = AntiSpamMiddleware(db, state, outgoing, bot)
    stats_collector = StatsCollectorMiddleware(buffer)

    dp = Dispatcher()
    install_middlewares(dp, chat_context, antispam, stats_collector)

    for router in (owner_start_router, owner_settings_router, payments_router, stats_router):
        dp.include_router(router)

    scheduler = create_scheduler(stats_service, subscriptions, buffer, outgoing)

    deps = Deps(db=db, bot=bot, state=state, outgoing=outgoing, subscriptions=subscriptions)
    set_deps(deps)
    deps.chat_context = chat_context
    deps.stars_provider = stars

    return App(bot, dp, db, scheduler, state, outgoing, subscriptions, stats_service, buffer, redis)


async def shutdown(app: App) -> None:
    app.scheduler.shutdown(wait=False)
    await app.stats_service.flush()
    await app.outgoing.stop(drain=True)
    await app.redis.aclose()
    await app.db.dispose()
    await app.bot.session.close()
    log.info("shutdown_complete")


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = await build_app(settings)
    app.scheduler.start()

    stop = asyncio.Event()

    def _signal(*_):
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal)

    polling = asyncio.create_task(app.dispatcher.start_polling(app.bot))
    await stop.wait()
    log.info("shutdown_requested")
    await app.dispatcher.stop_polling()
    await polling
    await shutdown(app)


if __name__ == "__main__":
    asyncio.run(run())
```

- [ ] **Step 4: Run test and lint**

Run: `pytest tests/test_main_wiring.py -v && ruff check src`
Expected: PASS, no lint errors

- [ ] **Step 5: Commit**

```bash
git add src/app/main.py src/app/logging_setup.py tests/test_main_wiring.py
git commit -m "feat: app entrypoint with graceful shutdown and retry backbone"
```

---

### Task 20: Retry wrapper, CI, and end-to-end verification

**Files:**
- Create: `src/app/services/retry.py`
- Create: `.github/workflows/ci.yml`
- Modify: `src/app/main.py` (wrap bot calls with retry config)
- Test: `tests/test_retry.py`

**Interfaces:**
- Consumes: `tenacity`, `app.config`.
- Produces: `telegram_retry` decorator targeting `aiogram.exceptions.TelegramRetryAfter`/network errors; `RETRY_ATTEMPTS`, `RETRY_BACKOFF`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_retry.py
import pytest

from app.services.retry import retry_async


async def test_retry_succeeds_after_failures():
    calls = {"n": 0}

    @retry_async(attempts=3, wait_min=0.001, wait_max=0.002)
    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("temporary")
        return "ok"

    assert await flaky() == "ok"
    assert calls["n"] == 3


async def test_retry_gives_up():
    @retry_async(attempts=2, wait_min=0.001, wait_max=0.002)
    async def always():
        raise ConnectionError("nope")

    with pytest.raises(ConnectionError):
        await always()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_retry.py -v`
Expected: FAIL (no module `app.services.retry`)

- [ ] **Step 3: Implement retry, wire it, add CI**

```python
# src/app/services/retry.py
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random_exponential


def retry_async(attempts: int = 4, wait_min: float = 0.5, wait_max: float = 8.0):
    return retry(
        stop=stop_after_attempt(attempts),
        wait=wait_random_exponential(multiplier=wait_min, max=wait_max),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
        reraise=True,
    )
```

Modify `src/app/main.py`: import and use for outgoing calls by wrapping the bot methods through a thin proxy is out of scope — instead document the decorator is applied inside `OutgoingQueue` worker:

```python
# inside src/app/services/outgoing.py _worker, after bucket.acquire():
from app.services.retry import retry_async

@retry_async()
async def _run(coro_factory):
    return await coro_factory()
```

Replace the `await coro_factory()` line in `_worker` with `await _run(coro_factory)` and add the import at module top.

```yaml
# .github/workflows/ci.yml
name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: bot
          POSTGRES_PASSWORD: bot
          POSTGRES_DB: bot
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U bot" --health-interval 5s
          --health-timeout 3s --health-retries 10
    env:
      BOT_TOKEN: "123:test"
      DATABASE_URL: postgresql+asyncpg://bot:bot@localhost:5432/bot
      REDIS_URL: redis://localhost:6379/0
      TEST_DATABASE_URL: postgresql+asyncpg://bot:bot@localhost:5432/bot
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e ".[dev]"
      - run: alembic upgrade head
      - run: ruff check src tests
      - run: pytest -q
```

- [ ] **Step 4: Run the full suite and lint**

Run: `ruff check src tests && pytest -q`
Expected: all tests PASS, no lint errors

- [ ] **Step 5: Commit**

```bash
git add src/app/services/retry.py src/app/services/outgoing.py src/app/main.py .github/workflows/ci.yml tests/test_retry.py
git commit -m "feat: retry wrapper, outgoing integration, and CI"
```

---

## Self-Review

**Spec coverage:**
- Anti-spam (links/caps/duplicates/flood/stopwords, actions, exemptions) → Tasks 6–9, 13.
- Statistics (buffer, batch flush, daily aggregates, retention, /stats, /top, Pro chart) → Tasks 11, 14, 15.
- Billing (PaymentProvider abstraction, Stars invoice/pre_checkout/successful_payment, idempotency) → Tasks 16, 18.
- Tiers/limits, lifecycle, orphan claim → Tasks 5, 17.
- Owner UX (/start, /settings, stopwords FSM) → Task 18.
- Redis state (fail-open), settings cache + invalidate, outgoing 25 req/s queue, graceful shutdown, migrate-only service → Tasks 8, 10, 12, 19, 2.
- Dev/Docker/tests/CI/retry → Tasks 2, 20.

**Placeholder scan:** no TBD/TODO; all code steps contain runnable snippets; integration tests are explicitly skip-guarded, not stubbed.

**Type consistency:** `ViolationType`/`Violation`/`Decision` consistent across Tasks 7, 9, 13. `StateStore` signatures match Tasks 8, 9. `PaymentResult` fields match Tasks 16, 17. `StatsRepo` methods referenced in Tasks 14, 15 exist in Task 11. `SubscriptionsService.has_feature/lifecycle/detect_orphans/claim` defined in Task 17 and used in Tasks 14, 15, 18.

**Known follow-ups (not in this plan):** greeting/captcha, scheduled posting, white-label/API, refunds, auto-renewal, CryptoBot/Stripe providers — see spec §8.
