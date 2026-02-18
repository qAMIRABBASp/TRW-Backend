import uuid
from dataclasses import dataclass


@dataclass
class PaymentInitResult:
    payment_url: str
    authority: str


@dataclass
class PaymentVerifyResult:
    success: bool
    ref_id: str | None = None
    raw_response: dict | None = None


class DummyGateway:
    def __init__(self, base_url: str = "http://127.0.0.1:5173"):
        self.base_url = base_url

    def init_payment(self, amount: int, callback_url: str) -> PaymentInitResult:
        authority = str(uuid.uuid4())
        payment_url = f"{self.base_url}/fake-gateway?authority={authority}"
        return PaymentInitResult(payment_url=payment_url, authority=authority)

    def verify_payment(self, authority: str) -> PaymentVerifyResult:
        ref_id = str(uuid.uuid4()).replace("-", "")[:16]
        return PaymentVerifyResult(success=True, ref_id=ref_id, raw_response={"authority": authority})
