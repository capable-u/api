from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.transaction import Transaction

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _serialize_transaction(tx: Transaction) -> dict:
    return {
        "id": tx.id,
        "booking_date": tx.booking_date.isoformat(),
        "value_date": tx.value_date.isoformat() if tx.value_date else None,
        "amount": float(tx.amount),
        "currency": tx.currency,
        "direction": tx.direction,
        "counterparty": tx.counterparty,
        "raw_description": tx.raw_description,
        "normalized_description": tx.normalized_description,
        "category": tx.category_id,
        "confidence": float(tx.confidence) if tx.confidence is not None else None,
        "duplicate_status": tx.duplicate_status,
        "duplicate_of_transaction_id": tx.duplicate_of_transaction_id,
        "duplicate_reason": tx.duplicate_reason,
        "duplicate_score": float(tx.duplicate_score) if tx.duplicate_score is not None else None,
    }


@router.get("")
def list_transactions(
        duplicate_status: str | None = Query(default=None),
        db: Session = Depends(get_db),
):
    query = select(Transaction)
    if duplicate_status:
        query = query.where(Transaction.duplicate_status == duplicate_status)

    items = db.execute(
        query.order_by(Transaction.booking_date.desc(), Transaction.id.desc())
    ).scalars().all()

    return [_serialize_transaction(tx) for tx in items]


@router.get("/review-queue")
def review_queue(
        limit: int = Query(default=50, ge=1, le=500),
        db: Session = Depends(get_db),
):
    items = db.execute(
        select(Transaction)
        .where(
            Transaction.duplicate_status == "possible_duplicate",
            Transaction.review_status == "pending",
        )
        .order_by(Transaction.booking_date.desc(), Transaction.id.desc())
        .limit(limit)
    ).scalars().all()

    return [_serialize_transaction(tx) for tx in items]
