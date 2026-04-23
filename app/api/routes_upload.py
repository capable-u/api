import asyncio
import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal, get_db
from app.models.import_job import ImportJob
from app.models.transaction import Transaction
from app.schemas.common import ErrorResponse
from app.models.enums import ImportJobStatus
from app.schemas.upload import (
    DeleteImportJobResponse,
    EnqueuedImportResponse,
    PaginatedImportJobsResponse,
)
from app.services.monthly_summary_service import rebuild_monthly_summaries_for_months
from app.worker.tasks import process_import_job

_TERMINAL_STATUSES = frozenset(
    {
        ImportJobStatus.done,
        ImportJobStatus.needs_review,
        ImportJobStatus.llm_failed,
        ImportJobStatus.failed,
    }
)
_SSE_POLL_INTERVAL = 1.5
_SSE_TIMEOUT_SECS = 600


def _sse_json_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Not serializable: {type(obj)}")


router = APIRouter(prefix="/imports", tags=["imports"])


def _get_import_job_or_404(db: Session, import_job_id: int) -> ImportJob:
    job = db.get(ImportJob, import_job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")
    return job


def _serialize_import_job(job: ImportJob) -> dict:
    return {
        "id": job.id,
        "filename": job.filename,
        "status": job.status,
        "total_transactions": job.total_transactions,
        "new_transactions": job.new_transactions,
        "duplicate_transactions": job.duplicate_transactions,
        "needs_review_count": job.needs_review_count,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


@router.get("", response_model=PaginatedImportJobsResponse)
def list_import_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    total = db.scalar(select(func.count(ImportJob.id))) or 0
    jobs = (
        db.execute(
            select(ImportJob)
            .order_by(ImportJob.created_at.desc(), ImportJob.id.desc())
            .offset(offset)
            .limit(limit)
        )
        .scalars()
        .all()
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_serialize_import_job(job) for job in jobs],
    }


@router.get(
    "/{import_job_id}/stream",
    responses={404: {"model": ErrorResponse}},
    response_class=StreamingResponse,
)
async def stream_import_status(import_job_id: int):
    with SessionLocal() as db:
        if db.get(ImportJob, import_job_id) is None:
            raise HTTPException(status_code=404, detail="Import job not found")

    async def event_generator():
        elapsed = 0.0
        last_status = None

        while elapsed < _SSE_TIMEOUT_SECS:
            with SessionLocal() as db:
                job = db.get(ImportJob, import_job_id)
                if job is None:
                    return
                current_status = job.status
                if current_status != last_status:
                    last_status = current_status
                    payload = _serialize_import_job(job)
                    yield f"data: {json.dumps(payload, default=_sse_json_default)}\n\n"
                is_terminal = current_status in _TERMINAL_STATUSES

            if is_terminal:
                return

            await asyncio.sleep(_SSE_POLL_INTERVAL)
            elapsed += _SSE_POLL_INTERVAL

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "",
    status_code=202,
    response_model=EnqueuedImportResponse,
    responses={
        400: {"model": ErrorResponse},
    },
)
async def upload_statement(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = upload_dir / file.filename
    content = await file.read()
    file_path.write_bytes(content)

    job = ImportJob(filename=file.filename, status=ImportJobStatus.uploaded)
    db.add(job)
    db.commit()
    db.refresh(job)

    process_import_job.delay(job.id, str(file_path))

    return {"import_job_id": job.id, "status": ImportJobStatus.uploaded}


@router.delete(
    "/{import_job_id}",
    response_model=DeleteImportJobResponse,
    responses={404: {"model": ErrorResponse}},
)
def delete_import_job(
    import_job_id: int,
    db: Session = Depends(get_db),
):
    job = _get_import_job_or_404(db, import_job_id)
    affected_months = set(
        db.execute(
            select(Transaction.booking_date)
            .where(Transaction.import_job_id == import_job_id)
            .distinct()
        )
        .scalars()
        .all()
    )

    db.delete(job)
    db.flush()
    rebuild_monthly_summaries_for_months(db=db, months=affected_months)
    db.commit()

    return {
        "id": import_job_id,
        "deleted": True,
    }
