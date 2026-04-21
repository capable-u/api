from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
import random

from app.schemas.transaction import ParsedTransaction


@dataclass(frozen=True)
class SyntheticGenerationConfig:
    transactions_count: int
    category_ids: list[int]
    other_category_id: int
    seed: int | None = None
    start_date: date | None = None
    end_date: date | None = None


def _build_date_range(
    rng: random.Random,
    start_date: date | None,
    end_date: date | None,
) -> tuple[date, date]:
    today = date.today()
    computed_end = end_date or today
    computed_start = start_date or (computed_end - timedelta(days=180))

    if computed_start > computed_end:
        computed_start, computed_end = computed_end, computed_start

    return computed_start, computed_end


def _random_booking_date(rng: random.Random, start_date: date, end_date: date) -> date:
    span = (end_date - start_date).days
    if span <= 0:
        return start_date
    return start_date + timedelta(days=rng.randint(0, span))


def _make_normalized_description(
    rng: random.Random, raw_description: str
) -> str | None:
    if rng.random() < 0.4:
        return None
    if rng.random() < 0.5:
        return f"  {raw_description.lower()}  "
    return raw_description.lower()


def _pick_category_id(
    rng: random.Random,
    category_ids: list[int],
    other_category_id: int,
) -> int:
    if rng.random() < 0.07:
        return max(category_ids, default=other_category_id) + rng.randint(1, 9)

    preferred_ids = [item for item in category_ids if item != other_category_id]
    source = preferred_ids or category_ids
    if not source:
        return other_category_id
    return rng.choice(source)


def _money(rng: random.Random) -> Decimal:
    value = Decimal(str(rng.uniform(5.0, 4200.0)))
    return value.quantize(Decimal("0.01"))


def _build_base_transaction(
    rng: random.Random,
    booking_date: date,
    category_ids: list[int],
    other_category_id: int,
) -> ParsedTransaction:
    direction = "income" if rng.random() < 0.35 else "expense"
    currency = rng.choice(["EUR", "USD", "GBP", "CHF"])

    counterparties = [
        "Acme GmbH",
        "Muster AG",
        "Tech Services Berlin",
        "Supermarkt Mitte",
        "City Transport",
        "Insurance North",
        None,
    ]
    descriptions = [
        "Salary transfer",
        "Apartment rent",
        "Grocery payment",
        "Fuel station",
        "Electricity bill",
        "Subscription renewal",
        "Restaurant card payment",
        "Online shopping order",
        "Health insurance premium",
        "Cash withdrawal ATM",
        "Tax office debit",
    ]

    raw_description = rng.choice(descriptions)
    counterparty = rng.choice(counterparties)

    return ParsedTransaction(
        booking_date=booking_date,
        amount=_money(rng),
        currency=currency,
        direction=direction,
        counterparty=counterparty,
        raw_description=raw_description,
        normalized_description=_make_normalized_description(rng, raw_description),
        category_id=_pick_category_id(rng, category_ids, other_category_id),
        confidence=round(rng.uniform(0.35, 0.99), 3),
    )


def _build_probable_duplicate(
    rng: random.Random,
    base: ParsedTransaction,
    start_date: date,
    end_date: date,
) -> ParsedTransaction:
    day_shift = rng.randint(-2, 2)
    shifted_date = base.booking_date + timedelta(days=day_shift)
    booking_date = min(max(shifted_date, start_date), end_date)

    counterparty = base.counterparty
    if counterparty and rng.random() < 0.6:
        counterparty = f"{counterparty} SE"

    raw_description = base.raw_description
    if rng.random() < 0.7:
        raw_description = f"{raw_description} monthly"

    return ParsedTransaction(
        booking_date=booking_date,
        amount=base.amount,
        currency=base.currency,
        direction=base.direction,
        counterparty=counterparty,
        raw_description=raw_description,
        normalized_description=_make_normalized_description(rng, raw_description),
        category_id=base.category_id,
        confidence=round(max(0.2, base.confidence - rng.uniform(0.0, 0.2)), 3),
    )


def _build_exact_duplicate(base: ParsedTransaction) -> ParsedTransaction:
    return ParsedTransaction(
        booking_date=base.booking_date,
        amount=base.amount,
        currency=base.currency,
        direction=base.direction,
        counterparty=base.counterparty,
        raw_description=base.raw_description,
        normalized_description=base.normalized_description,
        category_id=base.category_id,
        confidence=base.confidence,
    )


def _build_internal_transfer_pair(
    rng: random.Random,
    booking_date: date,
    category_ids: list[int],
    other_category_id: int,
) -> tuple[ParsedTransaction, ParsedTransaction]:
    amount = _money(rng)
    currency = rng.choice(["EUR", "USD"])
    category_id = _pick_category_id(rng, category_ids, other_category_id)

    outgoing = ParsedTransaction(
        booking_date=booking_date,
        amount=amount,
        currency=currency,
        direction="expense",
        counterparty="Own account",
        raw_description="Internal transfer",
        normalized_description="internal transfer",
        category_id=category_id,
        confidence=0.96,
    )
    incoming = ParsedTransaction(
        booking_date=booking_date + timedelta(days=rng.randint(0, 1)),
        amount=amount,
        currency=currency,
        direction="income",
        counterparty="Own account",
        raw_description="Transfer from own account",
        normalized_description="transfer from own account",
        category_id=category_id,
        confidence=0.96,
    )
    return outgoing, incoming


def generate_synthetic_transactions(
    config: SyntheticGenerationConfig,
) -> list[ParsedTransaction]:
    rng = random.Random(config.seed)
    start_date, end_date = _build_date_range(
        rng=rng,
        start_date=config.start_date,
        end_date=config.end_date,
    )

    items: list[ParsedTransaction] = []

    while len(items) < config.transactions_count:
        booking_date = _random_booking_date(rng, start_date, end_date)

        if len(items) + 2 <= config.transactions_count and rng.random() < 0.18:
            transfer_out, transfer_in = _build_internal_transfer_pair(
                rng=rng,
                booking_date=booking_date,
                category_ids=config.category_ids,
                other_category_id=config.other_category_id,
            )
            items.extend([transfer_out, transfer_in])
            continue

        base = _build_base_transaction(
            rng=rng,
            booking_date=booking_date,
            category_ids=config.category_ids,
            other_category_id=config.other_category_id,
        )
        items.append(base)

        if len(items) < config.transactions_count and rng.random() < 0.2:
            items.append(_build_probable_duplicate(rng, base, start_date, end_date))

        if len(items) < config.transactions_count and rng.random() < 0.12:
            items.append(_build_exact_duplicate(base))

    return items[: config.transactions_count]
