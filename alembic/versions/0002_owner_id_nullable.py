"""make chats.owner_id nullable

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-13
"""
import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("chats", "owner_id", existing_type=sa.BigInteger(), nullable=True)


def downgrade() -> None:
    op.alter_column("chats", "owner_id", existing_type=sa.BigInteger(), nullable=False)
