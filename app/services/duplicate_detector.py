from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from difflib import SequenceMatcher
import re

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.enums import DuplicateStatus
from app.models.transaction import Transaction
from app.services.fingerprint import normalize_text


PROBABLE_DATE_WINDOW_DAYS = 3
PROBABLE_SCORE_THRESHOLD = Decimal("0.80")
MAX_PROBABLE_CANDIDATES = 50
INTERNAL_TRANSFER_REASON = "internal_transfer"
INTERNAL_TRANSFER_SCORE = Decimal("0.950")
INTERNAL_TRANSFER_AMOUNT_TOLERANCE = Decimal("0.01")


@dataclass
class DuplicateMatch:
    status: DuplicateStatus
    duplicate_of_transaction_id: int | None = None
    duplicate_reason: str | None = None
    duplicate_score: Decimal | None = None


def _token_set(value: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", value.lower()) if token}


def _jaccard_similarity(left: str, right: str) -> float:
    left_tokens = _token_set(left)
    right_tokens = _token_set(right)
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0

    intersection = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    return intersection / union


def _text_similarity(left: str, right: str) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0

    sequence = SequenceMatcher(None, left, right).ratio()
    jaccard = _jaccard_similarity(left, right)
    return (sequence * 0.7) + (jaccard * 0.3)


def _counterparty_similarity(left: str | None, right: str | None) -> float:
    left_norm = normalize_text(left)
    right_norm = normalize_text(right)
    if not left_norm and not right_norm:
        return 1.0
    return _text_similarity(left_norm, right_norm)


def _quantize_score(score: float) -> Decimal:
    bounded = min(1.0, max(0.0, score))
    return Decimal(str(round(bounded, 3)))


def _probable_similarity_score(candidate: Transaction, raw_description: str, counterparty: str | None) -> Decimal:
    candidate_description = candidate.raw_description or normalize_text(candidate.raw_description)
    incoming_description = normalize_text(raw_description)

    description_score = _text_similarity(candidate_description, incoming_description)
    counterparty_score = _counterparty_similarity(candidate.counterparty, counterparty)

    weighted = (description_score * 0.8) + (counterparty_score * 0.2)
    return _quantize_score(weighted)


def _find_exact_duplicate(
        db: Session,
        fingerprint: str,
        exclude_transaction_id: int | None = None,
) -> Transaction | None:
    query = select(Transaction).where(Transaction.fingerprint == fingerprint)
    if exclude_transaction_id is not None:
        query = query.where(Transaction.id != exclude_transaction_id)

    return db.execute(
        query
        .order_by(Transaction.id.asc())
        .limit(1)
    ).scalar_one_or_none()


def _find_probable_candidates(
        db: Session,
        booking_date: date,
        amount: Decimal,
        currency: str,
        direction: str,
        exclude_transaction_id: int | None = None,
) -> list[Transaction]:
    from_date = booking_date - timedelta(days=PROBABLE_DATE_WINDOW_DAYS)
    to_date = booking_date + timedelta(days=PROBABLE_DATE_WINDOW_DAYS)

    conditions = [
        Transaction.amount == amount,
        Transaction.currency == currency,
        Transaction.direction == direction,
        Transaction.booking_date >= from_date,
        Transaction.booking_date <= to_date,
        Transaction.duplicate_status.in_(
            [
                DuplicateStatus.unique.value,
                DuplicateStatus.possible_duplicate.value,
            ]
        ),
    ]
    if exclude_transaction_id is not None:
        conditions.append(Transaction.id != exclude_transaction_id)

    return db.execute(
        select(Transaction)
        .where(and_(*conditions))
        .order_by(Transaction.booking_date.desc(), Transaction.id.desc())
        .limit(MAX_PROBABLE_CANDIDATES)
    ).scalars().all()


def _find_internal_transfer_candidate(
        db: Session,
        booking_date: date,
        amount: Decimal,
        currency: str,
        direction: str,
        exclude_transaction_id: int | None = None,
) -> Transaction | None:
    opposite_direction = "income" if direction == "expense" else "expense"
    from_date = booking_date - timedelta(days=PROBABLE_DATE_WINDOW_DAYS)
    to_date = booking_date + timedelta(days=PROBABLE_DATE_WINDOW_DAYS)
    min_amount = amount - INTERNAL_TRANSFER_AMOUNT_TOLERANCE
    max_amount = amount + INTERNAL_TRANSFER_AMOUNT_TOLERANCE

    conditions = [
        Transaction.currency == currency,
        Transaction.direction == opposite_direction,
        Transaction.amount >= min_amount,
        Transaction.amount <= max_amount,
        Transaction.booking_date >= from_date,
        Transaction.booking_date <= to_date,
        or_(
            Transaction.duplicate_reason.is_(None),
            Transaction.duplicate_reason != INTERNAL_TRANSFER_REASON,
        ),
    ]
    if exclude_transaction_id is not None:
        conditions.append(Transaction.id != exclude_transaction_id)

    return db.execute(
        select(Transaction)
        .where(and_(*conditions))
        .order_by(Transaction.booking_date.desc(), Transaction.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def detect_duplicate_match(
        db: Session,
        booking_date: date,
        amount: Decimal,
        currency: str,
        direction: str,
        raw_description: str,
        counterparty: str | None,
        fingerprint: str,
        exclude_transaction_id: int | None = None,
) -> DuplicateMatch:
    exact = _find_exact_duplicate(
        db,
        fingerprint=fingerprint,
        exclude_transaction_id=exclude_transaction_id,
    )
    if exact:
        return DuplicateMatch(
            status=DuplicateStatus.duplicate_confirmed,
            duplicate_of_transaction_id=exact.id,
            duplicate_reason="exact_fingerprint",
            duplicate_score=Decimal("1.000"),
        )

    internal_transfer_candidate = _find_internal_transfer_candidate(
        db=db,
        booking_date=booking_date,
        amount=amount,
        currency=currency,
        direction=direction,
        exclude_transaction_id=exclude_transaction_id,
    )
    if internal_transfer_candidate:
        return DuplicateMatch(
            status=DuplicateStatus.duplicate_confirmed,
            duplicate_of_transaction_id=internal_transfer_candidate.id,
            duplicate_reason=INTERNAL_TRANSFER_REASON,
            duplicate_score=INTERNAL_TRANSFER_SCORE,
        )

    candidates = _find_probable_candidates(
        db=db,
        booking_date=booking_date,
        amount=amount,
        currency=currency,
        direction=direction,
        exclude_transaction_id=exclude_transaction_id,
    )
    if not candidates:
        return DuplicateMatch(status=DuplicateStatus.unique)

    best_candidate: Transaction | None = None
    best_score = Decimal("0.000")

    for candidate in candidates:
        score = _probable_similarity_score(
            candidate=candidate,
            raw_description=raw_description,
            counterparty=counterparty,
        )
        if score > best_score:
            best_candidate = candidate
            best_score = score

    if best_candidate and best_score >= PROBABLE_SCORE_THRESHOLD:
        return DuplicateMatch(
            status=DuplicateStatus.possible_duplicate,
            duplicate_of_transaction_id=best_candidate.id,
            duplicate_reason="probable_similarity",
            duplicate_score=best_score,
        )

    return DuplicateMatch(status=DuplicateStatus.unique)


