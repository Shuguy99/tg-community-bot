from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
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
    owner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
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
        SAEnum(ViolationAction, name="violation_action", values_callable=lambda e: [m.value for m in e]),
        default=ViolationAction.DELETE,
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
    plan: Mapped[Plan] = mapped_column(
        SAEnum(Plan, name="plan", values_callable=lambda e: [m.value for m in e]), default=Plan.FREE
    )
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

    plan: Mapped[Plan] = mapped_column(
        SAEnum(Plan, name="plan", values_callable=lambda e: [m.value for m in e]), primary_key=True
    )
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
