from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.transaction import Transaction

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("")
def list_transactions(db: Session = Depends(get_db)):
    items = db.execute(
        select(Transaction).order_by(Transaction.booking_date.desc())
    ).scalars().all()

    return [
        {
            "id": tx.id,
            "booking_date": tx.booking_date.isoformat(),
            "value_date": tx.value_date.isoformat() if tx.value_date else None,
            "amount": float(tx.amount),
            "currency": tx.currency,
            "direction": tx.direction,
            "counterparty": tx.counterparty,
            "raw_description": tx.raw_description,
            "category": tx.category_id,
            "confidence": float(tx.confidence) if tx.confidence is not None else None,
        }
        for tx in items
    ]