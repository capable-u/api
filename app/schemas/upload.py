from datetime import date

from pydantic import AwareDatetime, BaseModel, Field


class UploadStatementResponse(BaseModel):
    import_job_id: int
    transactions_count: int
    new_transactions: int
    duplicate_transactions: int
    needs_review_count: int


class EnqueuedImportResponse(BaseModel):
    import_job_id: int
    status: str


class ImportJobResponse(BaseModel):
    id: int
    filename: str
    status: str
    total_transactions: int
    new_transactions: int
    duplicate_transactions: int
    needs_review_count: int
    created_at: AwareDatetime
    updated_at: AwareDatetime


class PaginatedImportJobsResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ImportJobResponse]


class DeleteImportJobResponse(BaseModel):
    id: int
    deleted: bool


class GenerateImportDataRequest(BaseModel):
    transactions_count: int = Field(default=250, ge=1, le=5000)
    seed: int | None = None
    dataset_name: str | None = Field(default=None, min_length=1, max_length=80)
    start_date: date | None = None
    end_date: date | None = None


class CleanupGeneratedImportsResponse(BaseModel):
    deleted_import_jobs: int
    deleted_transactions: int
