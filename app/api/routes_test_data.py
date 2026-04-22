import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.import_job import ImportJob
from app.models.transaction import Transaction
from app.schemas.common import ErrorResponse
from app.schemas.upload import (
    CleanupGeneratedImportsResponse,
    GenerateImportDataRequest,
    UploadStatementResponse,
)
from app.services.import_pipeline import ingest_transactions, load_categories
from app.services.monthly_summary_service import rebuild_monthly_summaries_for_months
from app.services.synthetic_data_generator import (
    SyntheticGenerationConfig,
    generate_synthetic_transactions,
)

GENERATED_FILENAME_PREFIX = "generated:"

router = APIRouter(tags=["test-data"])


@router.post(
    "/generate",
    response_model=UploadStatementResponse,
    responses={500: {"model": ErrorResponse}},
)
def generate_statement_data(
    payload: GenerateImportDataRequest,
    db: Session = Depends(get_db),
):
    try:
        categories, valid_category_ids, other_category = load_categories(db)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    category_ids = [item.id for item in categories]

    dataset_label = payload.dataset_name or "dataset"
    run_id = uuid.uuid4().hex[:8]
    synthetic_filename = f"{GENERATED_FILENAME_PREFIX}{dataset_label}_{payload.transactions_count}_{run_id}.pdf"

    job = ImportJob(filename=synthetic_filename, status="uploaded")
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        generated_transactions = generate_synthetic_transactions(
            SyntheticGenerationConfig(
                transactions_count=payload.transactions_count,
                category_ids=category_ids,
                other_category_id=other_category.id,
                seed=payload.seed,
                start_date=payload.start_date,
                end_date=payload.end_date,
            )
        )
        job.raw_text = (
            "Synthetic import generated without LLM. "
            f"seed={payload.seed} count={payload.transactions_count}"
        )
        job.status = "parsed_text"
        db.commit()

        job.status = "parsed_transactions"
        new_transactions, duplicate_transactions, needs_review_count = (
            ingest_transactions(
                db=db,
                job=job,
                transactions=generated_transactions,
                valid_category_ids=valid_category_ids,
                other_category=other_category,
            )
        )
        db.commit()

        return {
            "import_job_id": job.id,
            "transactions_count": len(generated_transactions),
            "new_transactions": new_transactions,
            "duplicate_transactions": duplicate_transactions,
            "needs_review_count": needs_review_count,
        }

    except Exception as e:
        db.rollback()
        job.status = "failed"
        db.add(job)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}") from e


@router.delete(
    "/generate",
    response_model=CleanupGeneratedImportsResponse,
    responses={500: {"model": ErrorResponse}},
)
def cleanup_generated_imports(
    db: Session = Depends(get_db),
):
    generated_job_ids = (
        db.execute(
            select(ImportJob.id).where(
                ImportJob.filename.like(f"{GENERATED_FILENAME_PREFIX}%")
            )
        )
        .scalars()
        .all()
    )

    if not generated_job_ids:
        return {"deleted_import_jobs": 0, "deleted_transactions": 0}

    deleted_transactions = (
        db.scalar(
            select(func.count(Transaction.id)).where(
                Transaction.import_job_id.in_(generated_job_ids)
            )
        )
        or 0
    )
    affected_months = set(
        db.execute(
            select(Transaction.booking_date)
            .where(Transaction.import_job_id.in_(generated_job_ids))
            .distinct()
        )
        .scalars()
        .all()
    )

    jobs = (
        db.execute(select(ImportJob).where(ImportJob.id.in_(generated_job_ids)))
        .scalars()
        .all()
    )
    for existing_job in jobs:
        db.delete(existing_job)

    db.flush()
    rebuild_monthly_summaries_for_months(db=db, months=affected_months)
    db.commit()

    return {
        "deleted_import_jobs": len(jobs),
        "deleted_transactions": int(deleted_transactions),
    }
