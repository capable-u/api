from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.category import Category
from app.models.enums import DuplicateStatus
from app.models.import_job import ImportJob
from app.schemas.upload import ImportJobStatus
from app.models.transaction import Transaction
from app.schemas.transaction import ParsedTransaction
from app.services.duplicate_detector import (
    INTERNAL_TRANSFER_REASON,
    detect_duplicate_match,
)
from app.services.exchange_rate_service import (
    ensure_rates_for_currencies,
    load_rates_lookup,
    resolve_amount_base,
)
from app.services.fingerprint import build_transaction_fingerprint, normalize_text
from app.services.monthly_summary_service import (
    month_start,
    rebuild_monthly_summaries_for_months,
)

CATEGORY_CONFIDENCE_PENALTY = 0.35


def _resolve_normalized_description(
    raw_description: str, llm_normalized_description: str | None
) -> str:
    if llm_normalized_description:
        cleaned = " ".join(llm_normalized_description.split()).strip()
        if cleaned:
            return cleaned
    return normalize_text(raw_description)


def _link_internal_transfer_pair(
    db: Session, tx: Transaction, counterpart_id: int, score
) -> Transaction | None:
    counterpart = db.get(Transaction, counterpart_id)
    if counterpart is None:
        return None

    tx.duplicate_status = DuplicateStatus.duplicate_confirmed.value
    tx.duplicate_of_transaction_id = counterpart.id
    tx.duplicate_reason = INTERNAL_TRANSFER_REASON
    tx.duplicate_score = score

    counterpart.duplicate_status = DuplicateStatus.duplicate_confirmed.value
    counterpart.duplicate_of_transaction_id = tx.id
    counterpart.duplicate_reason = INTERNAL_TRANSFER_REASON
    counterpart.duplicate_score = score

    db.add(counterpart)
    return counterpart


def load_categories(db: Session) -> tuple[list[Category], set[int], Category]:
    categories = (
        db.execute(select(Category).order_by(Category.id.asc())).scalars().all()
    )
    if not categories:
        raise ValueError("Categories are not initialized")

    valid_category_ids = {item.id for item in categories}
    other_category = next(
        (item for item in categories if item.name.strip().lower() == "other"), None
    )
    if other_category is None:
        raise ValueError('Category "Other" is not configured')

    return list(categories), valid_category_ids, other_category


def ingest_transactions(
    db: Session,
    job: ImportJob,
    transactions: list[ParsedTransaction],
    valid_category_ids: set[int],
    other_category: Category,
) -> tuple[int, int, int]:
    job.total_transactions = len(transactions)

    new_transactions = 0
    duplicate_transactions = 0
    needs_review_count = 0
    affected_months: set[date] = set()

    base_currency = settings.base_currency
    unique_currencies = {
        item.currency.strip().upper()
        for item in transactions
        if item.currency.strip().upper() != base_currency
    }

    if unique_currencies and transactions:
        all_dates = [item.booking_date for item in transactions]
        ensure_rates_for_currencies(
            db=db,
            base=base_currency,
            currencies=unique_currencies,
            start_date=min(all_dates),
            end_date=max(all_dates),
        )

    rates_lookup = load_rates_lookup(
        db=db, base=base_currency, currencies=unique_currencies
    )

    for item in transactions:
        category_id = item.category_id
        confidence = float(item.confidence)
        if category_id not in valid_category_ids:
            category_id = other_category.id
            confidence = max(0.0, confidence - CATEGORY_CONFIDENCE_PENALTY)

        normalized_currency = item.currency.strip().upper()
        normalized_direction = item.direction.strip().lower()
        fingerprint = build_transaction_fingerprint(
            booking_date=item.booking_date,
            amount=item.amount,
            currency=normalized_currency,
            direction=normalized_direction,
            raw_description=item.raw_description,
            counterparty=item.counterparty,
        )
        duplicate_match = detect_duplicate_match(
            db=db,
            booking_date=item.booking_date,
            amount=item.amount,
            currency=normalized_currency,
            direction=normalized_direction,
            raw_description=item.raw_description,
            counterparty=item.counterparty,
            fingerprint=fingerprint,
        )

        if (
            duplicate_match.status.value == DuplicateStatus.duplicate_confirmed.value
            and duplicate_match.duplicate_reason != INTERNAL_TRANSFER_REASON
        ):
            duplicate_transactions += 1
            continue

        absolute_amount = abs(item.amount)
        amount_base = resolve_amount_base(
            amount=absolute_amount,
            currency=normalized_currency,
            booking_date=item.booking_date,
            base=base_currency,
            rates_lookup=rates_lookup,
        )

        tx = Transaction(
            import_job_id=job.id,
            booking_date=item.booking_date,
            amount=absolute_amount,
            amount_base=amount_base,
            currency=normalized_currency,
            direction=normalized_direction,
            counterparty=item.counterparty,
            raw_description=item.raw_description,
            normalized_description=_resolve_normalized_description(
                raw_description=item.raw_description,
                llm_normalized_description=item.normalized_description,
            ),
            category_id=category_id,
            confidence=confidence,
            duplicate_status=duplicate_match.status.value,
            duplicate_of_transaction_id=duplicate_match.duplicate_of_transaction_id,
            duplicate_reason=duplicate_match.duplicate_reason,
            duplicate_score=duplicate_match.duplicate_score,
            fingerprint=fingerprint,
        )
        db.add(tx)
        db.flush()
        affected_months.add(month_start(tx.booking_date))

        if (
            duplicate_match.duplicate_reason == INTERNAL_TRANSFER_REASON
            and duplicate_match.duplicate_of_transaction_id is not None
        ):
            counterpart = _link_internal_transfer_pair(
                db=db,
                tx=tx,
                counterpart_id=duplicate_match.duplicate_of_transaction_id,
                score=duplicate_match.duplicate_score,
            )
            if counterpart is not None:
                affected_months.add(month_start(counterpart.booking_date))

        if duplicate_match.status.value == DuplicateStatus.unique.value:
            new_transactions += 1
        elif duplicate_match.status.value == DuplicateStatus.possible_duplicate.value:
            needs_review_count += 1
        elif duplicate_match.duplicate_reason == INTERNAL_TRANSFER_REASON:
            duplicate_transactions += 1

    job.new_transactions = new_transactions
    job.duplicate_transactions = duplicate_transactions
    job.needs_review_count = needs_review_count
    job.status = (
        ImportJobStatus.needs_review if needs_review_count > 0 else ImportJobStatus.done
    )
    rebuild_monthly_summaries_for_months(db=db, months=affected_months)

    return new_transactions, duplicate_transactions, needs_review_count
