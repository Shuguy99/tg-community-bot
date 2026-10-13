from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import (
    Chat,
    ChatAdmin,
    OwnershipClaim,
    Plan,
    Subscription,
    TierLimit,
    Transaction,
)
from app.services.payments.provider import PaymentResult

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

    async def activate(self, result: PaymentResult) -> None:
        plan = Plan(result.plan)
        now = datetime.now(UTC)
        expires = now + timedelta(days=30)
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
                .values(
                    chat_id=result.chat_id,
                    plan=plan,
                    started_at=now,
                    expires_at=expires,
                    is_active=True,
                )
                .on_conflict_do_update(
                    index_elements=[Subscription.chat_id],
                    set_={"plan": plan, "expires_at": expires, "is_active": True},
                )
            )
            await session.execute(stmt)
            await session.commit()
        log.info("subscription_activated", chat_id=result.chat_id, plan=plan.value)

    async def lifecycle(self) -> None:
        now = datetime.now(UTC)
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
            chats = list(
                (await session.execute(select(Chat).where(Chat.is_active.is_(True)))).scalars()
            )
        for chat in chats:
            try:
                admins = await self._bot.get_chat_administrators(chat.id)
            except Exception as exc:
                log.debug("orphan_check_failed", chat_id=chat.id, error=str(exc))
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
            session.add(
                OwnershipClaim(chat_id=chat_id, claimant_id=claimant_id, prev_owner_id=prev)
            )
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
        except Exception as exc:
            log.debug("notify_failed", chat_id=chat_id, error=str(exc))
