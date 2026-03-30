from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.enums import DuplicateStatus
from app.models.import_job import ImportJob
from app.models.transaction import Transaction
from app.schemas.common import ErrorResponse
from app.schemas.transaction import (
    DeleteTransactionResponse,
    TransactionDetailResponse,
    TransactionSummaryResponse,
    TransactionUpdateRequest,
)
from app.services.duplicate_detector import detect_duplicate_match
from app.services.fingerprint import build_transaction_fingerprint

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
            "created_at": tx.created_at.isoformat(),
            "updated_at": tx.updated_at.isoformat(),
        }
    )
    return payload


def _serialize_transaction(tx: Transaction) -> dict:
    return {
        "id": tx.id,
        "booking_date": tx.booking_date.isoformat(),
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


@router.get("", response_model=list[TransactionSummaryResponse])
def list_transactions(
        duplicate_status: DuplicateStatus | None = Query(default=None),
        db: Session = Depends(get_db),
):
    query = select(Transaction)
    if duplicate_status:
        query = query.where(Transaction.duplicate_status == duplicate_status.value)

    items = db.execute(
        query.order_by(Transaction.booking_date.desc(), Transaction.id.desc())
    ).scalars().all()

    return [_serialize_transaction(tx) for tx in items]


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

    fingerprint_changed_fields = {
        "booking_date",
        "amount",
        "currency",
        "direction",
        "counterparty",
    }
    should_rebuild_fingerprint = any(field in update_data for field in fingerprint_changed_fields)

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

    db.add(tx)
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

    db.delete(tx)
    if job:
        db.add(job)
    db.commit()

    return {
        "id": transaction_id,
        "deleted": True,
        "action": "deleted",
    }
