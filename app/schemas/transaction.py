from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field



class ParsedTransaction(BaseModel):
    booking_date: date
    value_date: date | None = None
    amount: Decimal
    currency: str = "EUR"
    direction: str = Field(pattern="^(income|expense)$")
    counterparty: str | None = None
    raw_description: str
    category_id: int
    confidence: float = Field(ge=0.0, le=1.0)


class ParsedTransactionsResponse(BaseModel):
    transactions: list[ParsedTransaction]


class TransactionUpdateRequest(BaseModel):
    booking_date: date | None = None
    value_date: date | None = None
    amount: Decimal | None = None
    currency: str | None = None
    direction: str | None = Field(default=None, pattern="^(income|expense)$")
    counterparty: str | None = None
    raw_description: str | None = None
    category_id: int | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
