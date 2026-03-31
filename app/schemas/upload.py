from datetime import datetime
from pydantic import BaseModel


class UploadStatementResponse(BaseModel):
    import_job_id: int
    transactions_count: int
    new_transactions: int
    duplicate_transactions: int
    needs_review_count: int


class ImportJobResponse(BaseModel):
    id: int
    filename: str
    status: str
    total_transactions: int
    new_transactions: int
    duplicate_transactions: int
    needs_review_count: int
    created_at: datetime
    updated_at: datetime


class PaginatedImportJobsResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ImportJobResponse]


class DeleteImportJobResponse(BaseModel):
    id: int
    deleted: bool


