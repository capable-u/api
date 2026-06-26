import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx
import redis
from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.exchange_rate import ExchangeRate
from app.models.transaction import Transaction

FRANKFURTER_BASE_URL = "https://api.frankfurter.dev/v2"

_CURRENCIES_REDIS_KEY = "capable_u:currencies"
_CURRENCIES_CACHE_TTL_SECS = 86400  # 24 h

_redis_client: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


def fetch_available_currencies() -> set[str]:
    """Return valid ISO currency codes from Frankfurter. Cached in Redis for 24 h."""
    r = _get_redis()
    cached = r.get(_CURRENCIES_REDIS_KEY)
    if cached:
        return set(json.loads(cached))
    response = httpx.get(f"{FRANKFURTER_BASE_URL}/currencies", timeout=10)
    response.raise_for_status()
    currencies = {item["iso_code"] for item in response.json()}
    r.setex(
        _CURRENCIES_REDIS_KEY, _CURRENCIES_CACHE_TTL_SECS, json.dumps(list(currencies))
    )
    return currencies


# ---------------------------------------------------------------------------
# Low-level API + storage helpers
# ---------------------------------------------------------------------------


def _fetch_rates(
    base: str,
    targets: set[str],
    start_date: date,
    end_date: date,
) -> list[dict]:
    response = httpx.get(
        f"{FRANKFURTER_BASE_URL}/rates",
        params={
            "base": base,
            "from": str(start_date),
            "to": str(end_date),
            "quotes": ",".join(sorted(targets)),
        },
        timeout=30,
    )
    response.raise_for_status()
    # v2: flat array [{date, base, quote, rate}, ...]
    return [r for r in response.json() if r["quote"] in targets]


def _store_rates(db: Session, records: list[dict]) -> int:
    """Upsert rate records into exchange_rates. Returns rowcount."""
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
    return result.rowcount


# ---------------------------------------------------------------------------
# Ensure rates coverage for a date range
# ---------------------------------------------------------------------------


def ensure_rates_for_currencies(
    db: Session,
    base: str,
    currencies: set[str],
    start_date: date,
    end_date: date,
) -> None:
    """Ensure DB has rates for every currency over [start_date, end_date].

    Checks both direct (base→currency) and reverse (currency→base) coverage so
    that already-stored pairs are never re-fetched.  Only the genuinely missing
    sub-ranges are requested from the API.
    """
    if not currencies:
        return

    today = datetime.now(tz=timezone.utc).date()
    effective_end = min(end_date, today)

    to_fetch: dict[str, tuple[date, date]] = {}

    for currency in currencies:
        row = db.execute(
            select(
                func.min(ExchangeRate.date).label("min_date"),
                func.max(ExchangeRate.date).label("max_date"),
            ).where(
                or_(
                    and_(
                        ExchangeRate.base_currency == base,
                        ExchangeRate.target_currency == currency,
                    ),
                    and_(
                        ExchangeRate.base_currency == currency,
                        ExchangeRate.target_currency == base,
                    ),
                )
            )
        ).one()

        db_min: date | None = row.min_date
        db_max: date | None = row.max_date

        if db_min is None:
            # No rates at all for this pair
            to_fetch[currency] = (start_date, effective_end)
        else:
            needs_older = start_date < db_min
            needs_newer = effective_end > db_max

            if needs_older and needs_newer:
                to_fetch[currency] = (start_date, effective_end)
            elif needs_older:
                to_fetch[currency] = (start_date, db_min - timedelta(days=1))
            elif needs_newer:
                to_fetch[currency] = (db_max + timedelta(days=1), effective_end)

    if not to_fetch:
        return

    # Single API call covering the union of all missing ranges
    fetch_start = min(v[0] for v in to_fetch.values())
    fetch_end = max(v[1] for v in to_fetch.values())

    records = _fetch_rates(base, set(to_fetch.keys()), fetch_start, fetch_end)
    _store_rates(db, records)


# ---------------------------------------------------------------------------
# Rate lookup helpers (used when computing amount_base)
# ---------------------------------------------------------------------------


def load_rates_lookup(
    db: Session,
    base: str,
    currencies: set[str],
) -> dict[str, list[tuple[date, Decimal]]]:
    """Return {currency: [(date, effective_rate), ...]} sorted by date asc.

    Loads both direct (base→currency) and reverse (currency→base) rates and
    normalises them to base→currency direction.  Direct rates win over reverse
    for the same date.
    """
    if not currencies:
        return {}

    # Direct: base → target
    direct_rows = db.execute(
        select(ExchangeRate.target_currency, ExchangeRate.date, ExchangeRate.rate)
        .where(
            ExchangeRate.base_currency == base,
            ExchangeRate.target_currency.in_(currencies),
        )
        .order_by(ExchangeRate.date.asc())
    ).all()

    # Reverse: target → base  (invert so result is base→target)
    reverse_rows = db.execute(
        select(
            ExchangeRate.base_currency.label("currency"),
            ExchangeRate.date,
            ExchangeRate.rate,
        )
        .where(
            ExchangeRate.target_currency == base,
            ExchangeRate.base_currency.in_(currencies),
        )
        .order_by(ExchangeRate.date.asc())
    ).all()

    # Merge into {currency: {date: rate}} — direct takes precedence
    by_date: dict[str, dict[date, Decimal]] = {}

    for row in reverse_rows:
        inverted = (Decimal(1) / row.rate).quantize(Decimal("0.000001"))
        by_date.setdefault(row.currency, {})[row.date] = inverted

    for row in direct_rows:
        by_date.setdefault(row.target_currency, {})[row.date] = row.rate

    return {
        currency: sorted(date_rates.items()) for currency, date_rates in by_date.items()
    }


def resolve_amount_base(
    amount: Decimal,
    currency: str,
    booking_date: date,
    base: str,
    rates_lookup: dict[str, list[tuple[date, Decimal]]],
) -> Decimal | None:
    """Convert amount to base currency using the most recent available rate.

    The lookup already normalises rates to base→currency direction, so:
        base_amount = currency_amount / rate
    """
    if currency == base:
        return amount

    entries = rates_lookup.get(currency)
    if not entries:
        return None

    # Entries sorted ascending; find last one on or before booking_date.
    rate: Decimal | None = None
    for entry_date, entry_rate in entries:
        if entry_date <= booking_date:
            rate = entry_rate
        else:
            break

    if rate is None:
        return None

    return (amount / rate).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Bulk update (POST /exchange-rates/update endpoint)
# ---------------------------------------------------------------------------


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

    count = _store_rates(db, records)
    db.commit()
    return count
