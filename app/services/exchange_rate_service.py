from datetime import date, datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.exchange_rate import ExchangeRate
from app.models.transaction import Transaction

FRANKFURTER_BASE_URL = "https://api.frankfurter.dev/v2"

# ---------------------------------------------------------------------------
# Rate lookup helpers (used during transaction ingestion)
# ---------------------------------------------------------------------------


def load_rates_lookup(
    db: Session,
    base: str,
    currencies: set[str],
) -> dict[str, list[tuple[date, Decimal]]]:
    """Return {target_currency: [(date, rate), ...]} sorted by date ascending."""
    if not currencies:
        return {}
    rows = db.execute(
        select(ExchangeRate.target_currency, ExchangeRate.date, ExchangeRate.rate)
        .where(
            ExchangeRate.base_currency == base,
            ExchangeRate.target_currency.in_(currencies),
        )
        .order_by(ExchangeRate.date.asc())
    ).all()
    lookup: dict[str, list[tuple[date, Decimal]]] = {}
    for row in rows:
        lookup.setdefault(row.target_currency, []).append((row.date, row.rate))
    return lookup


def resolve_amount_base(
    amount: Decimal,
    currency: str,
    booking_date: date,
    base: str,
    rates_lookup: dict[str, list[tuple[date, Decimal]]],
) -> Decimal | None:
    """Convert amount to base currency using the most recent available rate.

    The rate table stores base→target rates, so to convert target→base we invert:
        base_amount = target_amount / rate
    """
    if currency == base:
        return amount

    entries = rates_lookup.get(currency)
    if not entries:
        return None

    # Entries sorted ascending by date; find the last one on or before booking_date.
    rate: Decimal | None = None
    for entry_date, entry_rate in entries:
        if entry_date <= booking_date:
            rate = entry_rate
        else:
            break

    if rate is None:
        return None

    return (amount / rate).quantize(Decimal("0.01"))


def _fetch_rates(
    base: str,
    targets: set[str],
    start_date: date,
    end_date: date,
) -> list[dict]:
    response = httpx.get(
        f"{FRANKFURTER_BASE_URL}/rates",
        params={"base": base, "from": str(start_date), "to": str(end_date)},
        timeout=30,
    )
    response.raise_for_status()
    # v2 returns a flat array: [{"date": "...", "base": "EUR", "quote": "USD", "rate": 1.05}, ...]
    return [r for r in response.json() if r["quote"] in targets]


def update_exchange_rates(db: Session) -> int:
    earliest_date: date | None = db.execute(
        select(func.min(Transaction.booking_date))
    ).scalar_one_or_none()

    if earliest_date is None:
        return 0

    currencies: list[str] = list(
        db.execute(select(Transaction.currency).distinct()).scalars().all()
    )

    base = settings.base_currency
    targets = {c for c in currencies if c != base}

    if not targets:
        return 0

    today = datetime.now(tz=timezone.utc).date()
    records = _fetch_rates(base, targets, earliest_date, today)

    if not records:
        return 0

    now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    rows = [
        {
            "date": date.fromisoformat(r["date"]),
            "base_currency": r["base"],
            "target_currency": r["quote"],
            "rate": Decimal(str(r["rate"])),
            "created_at": now,
            "updated_at": now,
        }
        for r in records
    ]

    stmt = insert(ExchangeRate).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_exchange_rates_date_base_target",
        set_={"rate": stmt.excluded.rate, "updated_at": stmt.excluded.updated_at},
    )
    result = db.execute(stmt)
    db.commit()

    return result.rowcount
