from pydantic import BaseModel


class UploadStatementResponse(BaseModel):
    import_job_id: int
    transactions_count: int
    new_transactions: int
    duplicate_transactions: int
    needs_review_count: int

