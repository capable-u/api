from datetime import date
from decimal import Decimal
from pydantic import AwareDatetime, BaseModel, Field


class ParsedTransaction(BaseModel):
    booking_date: date
    amount: Decimal
    currency: str = "EUR"
    direction: str = Field(pattern="^(income|expense)$")
    counterparty: str | None = None
    raw_description: str
    normalized_description: str | None = Field(
        default=None, min_length=1, max_length=180
    )
    category_id: int
    confidence: float = Field(ge=0.0, le=1.0)


class ParsedTransactionsResponse(BaseModel):
    transactions: list[ParsedTransaction]


class TransactionUpdateRequest(BaseModel):
    booking_date: date | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=10)
    direction: str | None = Field(default=None, pattern="^(income|expense)$")
    counterparty: str | None = None
    normalized_description: str | None = None
    category_id: int | None = Field(default=None, gt=0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class TransactionSummaryResponse(BaseModel):
    id: int
    booking_date: date
    amount: float
    currency: str
    direction: str
    counterparty: str | None = None
    raw_description: str
    normalized_description: str
    category_id: int
    confidence: float | None = None
    duplicate_status: str
    duplicate_of_transaction_id: int | None = None
    duplicate_reason: str | None = None
    duplicate_score: float | None = None


class TransactionDetailResponse(TransactionSummaryResponse):
    import_job_id: int
    fingerprint: str
    created_at: AwareDatetime
    updated_at: AwareDatetime


class PaginatedTransactionsResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[TransactionSummaryResponse]


class DeleteTransactionResponse(BaseModel):
    id: int
    deleted: bool
