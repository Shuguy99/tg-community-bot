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
