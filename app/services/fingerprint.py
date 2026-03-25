import hashlib
import re
from datetime import date
from decimal import Decimal


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = value.lower().strip()
    value = re.sub(r"\s+", " ", value)
    return value


def build_transaction_fingerprint(
        booking_date: date,
        amount: Decimal,
        direction: str,
        raw_description: str,
        counterparty: str | None,
) -> str:
    payload = "|".join(
        [
            booking_date.isoformat(),
            str(amount),
            direction.strip().lower(),
            normalize_text(counterparty),
            normalize_text(raw_description),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()