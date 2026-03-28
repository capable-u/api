import hashlib
import re
from datetime import date
from decimal import Decimal


FINGERPRINT_VERSION = "v2"


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = value.lower().strip()
    value = re.sub(r"\s+", " ", value)
    return value


def normalize_amount(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def build_transaction_fingerprint(
        booking_date: date,
        amount: Decimal,
        currency: str,
        direction: str,
        raw_description: str,
        counterparty: str | None,
) -> str:
    payload = "|".join(
        [
            FINGERPRINT_VERSION,
            booking_date.isoformat(),
            normalize_amount(amount),
            currency.strip().upper(),
            direction.strip().lower(),
            normalize_text(counterparty),
            normalize_text(raw_description),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()