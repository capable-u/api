from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.enums import DuplicateStatus
from app.models.import_job import ImportJob
from app.models.monthly_category_summary import MonthlyCategorySummary
from app.models.monthly_summary import MonthlySummary
from app.models.transaction import Transaction
from app.schemas.common import ErrorResponse
from app.schemas.monthly_summary import MonthlyOverviewResponse
from app.schemas.transaction import (
    DeleteTransactionResponse,
    PaginatedTransactionsResponse,
    TransactionDetailResponse,
    TransactionSummaryResponse,
    TransactionUpdateRequest,
)
from app.services.duplicate_detector import detect_duplicate_match
from app.services.fingerprint import build_transaction_fingerprint
from app.services.monthly_summary_service import month_start, rebuild_monthly_summaries_for_months

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _get_transaction_or_404(db: Session, transaction_id: int) -> Transaction:
    tx = db.get(Transaction, transaction_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return tx


def _apply_review_job_counters(job: ImportJob | None, was_possible_duplicate: bool, resolved_as_duplicate: bool) -> None:
    if not job or not was_possible_duplicate:
        return

    job.needs_review_count = max(0, job.needs_review_count - 1)
    if resolved_as_duplicate:
        job.duplicate_transactions += 1
    else:
        job.new_transactions += 1

    job.status = "needs_review" if job.needs_review_count > 0 else "done"


def _apply_delete_job_counters(job: ImportJob | None, tx: Transaction) -> None:
    if not job:
        return

    if tx.duplicate_status == DuplicateStatus.unique.value:
        job.new_transactions = max(0, job.new_transactions - 1)
    elif tx.duplicate_status == DuplicateStatus.duplicate_confirmed.value:
        job.duplicate_transactions = max(0, job.duplicate_transactions - 1)
    elif tx.duplicate_status == DuplicateStatus.possible_duplicate.value:
        job.needs_review_count = max(0, job.needs_review_count - 1)

    job.status = "needs_review" if job.needs_review_count > 0 else "done"


def _serialize_transaction_full(tx: Transaction) -> dict:
    payload = _serialize_transaction(tx)
    payload.update(
        {
            "import_job_id": tx.import_job_id,
            "fingerprint": tx.fingerprint,
            "created_at": tx.created_at,
            "updated_at": tx.updated_at,
        }
    )
    return payload


def _serialize_transaction(tx: Transaction) -> dict:
    return {
        "id": tx.id,
        "booking_date": tx.booking_date,
        "amount": float(tx.amount),
        "currency": tx.currency,
        "direction": tx.direction,
        "counterparty": tx.counterparty,
        "raw_description": tx.raw_description,
        "normalized_description": tx.normalized_description,
        "category_id": tx.category_id,
        "confidence": float(tx.confidence) if tx.confidence is not None else None,
        "duplicate_status": tx.duplicate_status,
        "duplicate_of_transaction_id": tx.duplicate_of_transaction_id,
        "duplicate_reason": tx.duplicate_reason,
        "duplicate_score": float(tx.duplicate_score) if tx.duplicate_score is not None else None,
    }


@router.get("", response_model=PaginatedTransactionsResponse)
def list_transactions(
        duplicate_status: DuplicateStatus | None = Query(default=None),
        import_job_id: int | None = Query(default=None, ge=1),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        db: Session = Depends(get_db),
):
    filters = []
    if duplicate_status:
        filters.append(Transaction.duplicate_status == duplicate_status.value)
    if import_job_id is not None:
        filters.append(Transaction.import_job_id == import_job_id)

    query = select(Transaction)
    if filters:
        query = query.where(*filters)

    total = db.scalar(select(func.count(Transaction.id)).where(*filters)) or 0

    items = db.execute(
        query.order_by(Transaction.booking_date.desc(), Transaction.id.desc()).offset(offset).limit(limit)
    ).scalars().all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_serialize_transaction(tx) for tx in items],
    }


@router.get("/monthly-summary", response_model=MonthlyOverviewResponse)
def get_monthly_summary(
        month_from: date | None = Query(default=None),
        month_to: date | None = Query(default=None),
        currency: str | None = Query(default=None, min_length=3, max_length=10),
        db: Session = Depends(get_db),
):
    if month_from and month_to and month_from > month_to:
        raise HTTPException(status_code=400, detail="month_from must be less than or equal to month_to")

    normalized_currency = currency.strip().upper() if currency else None

    summary_filters = []
    category_filters = []

    if month_from is not None:
        summary_filters.append(MonthlySummary.month >= month_from)
        category_filters.append(MonthlyCategorySummary.month >= month_from)
    if month_to is not None:
        summary_filters.append(MonthlySummary.month <= month_to)
        category_filters.append(MonthlyCategorySummary.month <= month_to)
    if normalized_currency is not None:
        summary_filters.append(MonthlySummary.currency == normalized_currency)
        category_filters.append(MonthlyCategorySummary.currency == normalized_currency)

    summary_rows = db.execute(
        select(MonthlySummary)
        .where(*summary_filters)
        .order_by(MonthlySummary.month.desc(), MonthlySummary.currency.asc())
    ).scalars().all()

    category_rows = db.execute(
        select(
            MonthlyCategorySummary.month,
            MonthlyCategorySummary.currency,
            MonthlyCategorySummary.category_id,
            MonthlyCategorySummary.expense_total,
        )
        .where(*category_filters)
        .order_by(
            MonthlyCategorySummary.month.desc(),
            MonthlyCategorySummary.currency.asc(),
            MonthlyCategorySummary.category_id.asc(),
        )
    ).all()

    return {
        "month_from": month_from,
        "month_to": month_to,
        "currency": normalized_currency,
        "summaries": [
            {
                "month": row.month,
                "currency": row.currency,
                "income_total": float(row.income_total),
                "expense_total": float(row.expense_total),
            }
            for row in summary_rows
        ],
        "category_summaries": [
            {
                "month": row.month,
                "currency": row.currency,
                "category_id": row.category_id,
                "expense_total": float(row.expense_total),
            }
            for row in category_rows
        ],
    }


@router.get(
    "/{transaction_id}",
    response_model=TransactionDetailResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_transaction_by_id(
        transaction_id: int,
        db: Session = Depends(get_db),
):
    tx = _get_transaction_or_404(db, transaction_id)
    return _serialize_transaction_full(tx)


@router.post(
    "/{transaction_id}/mark-unique",
    response_model=TransactionSummaryResponse,
    responses={404: {"model": ErrorResponse}},
)
def mark_transaction_as_unique(
        transaction_id: int,
        db: Session = Depends(get_db),
):
    tx = _get_transaction_or_404(db, transaction_id)
    was_possible_duplicate = tx.duplicate_status == DuplicateStatus.possible_duplicate.value
    job = db.get(ImportJob, tx.import_job_id)

    tx.duplicate_status = DuplicateStatus.unique.value
    tx.duplicate_of_transaction_id = None
    tx.duplicate_reason = None
    tx.duplicate_score = None

    _apply_review_job_counters(
        job=job,
        was_possible_duplicate=was_possible_duplicate,
        resolved_as_duplicate=False,
    )

    db.add(tx)
    if job:
        db.add(job)
    db.flush()
    rebuild_monthly_summaries_for_months(db=db, months={month_start(tx.booking_date)})
    db.commit()
    db.refresh(tx)

    return _serialize_transaction(tx)


@router.patch(
    "/{transaction_id}",
    response_model=TransactionDetailResponse,
    responses={404: {"model": ErrorResponse}},
)
def update_transaction(
        transaction_id: int,
        payload: TransactionUpdateRequest,
        db: Session = Depends(get_db),
):
    tx = _get_transaction_or_404(db, transaction_id)

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        return _serialize_transaction_full(tx)

    old_month = month_start(tx.booking_date)

    fingerprint_changed_fields = {
        "booking_date",
        "amount",
        "currency",
        "direction",
        "counterparty",
    }
    should_rebuild_fingerprint = any(field in update_data for field in fingerprint_changed_fields)
    summary_changed_fields = {
        "booking_date",
        "amount",
        "currency",
        "direction",
        "category_id",
        "counterparty",
    }
    should_rebuild_summary = any(field in update_data for field in summary_changed_fields)

    for field, value in update_data.items():
        if field == "currency" and value is not None:
            setattr(tx, field, value.strip().upper())
            continue
        if field == "direction" and value is not None:
            setattr(tx, field, value.strip().lower())
            continue
        setattr(tx, field, value)


    if should_rebuild_fingerprint:
        tx.fingerprint = build_transaction_fingerprint(
            booking_date=tx.booking_date,
            amount=tx.amount,
            currency=tx.currency,
            direction=tx.direction,
            raw_description=tx.raw_description,
            counterparty=tx.counterparty,
        )
        duplicate_match = detect_duplicate_match(
            db=db,
            booking_date=tx.booking_date,
            amount=tx.amount,
            currency=tx.currency,
            direction=tx.direction,
            raw_description=tx.raw_description,
            counterparty=tx.counterparty,
            fingerprint=tx.fingerprint,
            exclude_transaction_id=tx.id,
        )
        tx.duplicate_status = duplicate_match.status.value
        tx.duplicate_of_transaction_id = duplicate_match.duplicate_of_transaction_id
        tx.duplicate_reason = duplicate_match.duplicate_reason
        tx.duplicate_score = duplicate_match.duplicate_score
        should_rebuild_summary = True

    db.add(tx)
    db.flush()
    if should_rebuild_summary:
        rebuild_monthly_summaries_for_months(
            db=db,
            months={old_month, month_start(tx.booking_date)},
        )
    db.commit()
    db.refresh(tx)

    return _serialize_transaction_full(tx)


@router.delete(
    "/{transaction_id}",
    response_model=DeleteTransactionResponse,
    responses={404: {"model": ErrorResponse}},
)
def delete_transaction(
        transaction_id: int,
        db: Session = Depends(get_db),
):
    tx = _get_transaction_or_404(db, transaction_id)
    job = db.get(ImportJob, tx.import_job_id)

    _apply_delete_job_counters(job=job, tx=tx)
    affected_month = month_start(tx.booking_date)

    db.delete(tx)
    db.flush()
    rebuild_monthly_summaries_for_months(db=db, months={affected_month})
    if job:
        db.add(job)
    db.commit()

    return {
        "id": transaction_id,
        "deleted": True,
    }
