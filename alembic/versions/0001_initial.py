"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-12
"""
import sqlalchemy as sa

from alembic import op
from app.db import models  # noqa: F401
from app.db.base import Base

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
    return sa.table(
        "tier_limits",
        sa.column("plan", sa.String),
        sa.column("max_members", sa.Integer),
        sa.column("price_stars", sa.Integer),
        sa.column("features", sa.dialects.postgresql.JSONB),
    )
