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
