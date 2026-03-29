from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.category import Category
from app.core.db import get_db
from app.core.config import settings
from app.models.enums import DuplicateStatus
from app.models.import_job import ImportJob
from app.models.transaction import Transaction
from app.services.pdf_extract import extract_text_with_pypdf
from app.services.transaction_parser import parse_transactions_from_text
from app.services.duplicate_detector import detect_duplicate_match
from app.services.fingerprint import build_transaction_fingerprint, normalize_text
from app.services.llm_client import LLMClientError
from app.schemas.common import ErrorResponse
from app.schemas.upload import UploadStatementResponse

router = APIRouter(prefix="/imports", tags=["imports"])

CATEGORY_CONFIDENCE_PENALTY = 0.35


def _resolve_normalized_description(raw_description: str, llm_normalized_description: str | None) -> str:
    if llm_normalized_description:
        cleaned = " ".join(llm_normalized_description.split()).strip()
        if cleaned:
            return cleaned
    return normalize_text(raw_description)


@router.post(
    "",
    response_model=UploadStatementResponse,
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
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

    job = ImportJob(filename=file.filename, status="uploaded")
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        categories = db.execute(select(Category).order_by(Category.id.asc())).scalars().all()
        if not categories:
            raise HTTPException(status_code=500, detail="Categories are not initialized")

        category_pairs = [(item.id, item.name) for item in categories]
        valid_category_ids = {item.id for item in categories}
        other_category = next((item for item in categories if item.name.strip().lower() == "other"), None)
        if other_category is None:
            raise HTTPException(status_code=500, detail='Category "Other" is not configured')

        raw_text = extract_text_with_pypdf(str(file_path))
        job.raw_text = raw_text
        job.status = "parsed_text"
        db.commit()

        parsed = await parse_transactions_from_text(raw_text, categories=category_pairs)
        job.status = "parsed_transactions"
        job.total_transactions = len(parsed.transactions)

        new_transactions = 0
        duplicate_transactions = 0
        needs_review_count = 0

        for item in parsed.transactions:
            category_id = item.category_id
            confidence = float(item.confidence)
            if category_id not in valid_category_ids:
                category_id = other_category.id
                confidence = max(0.0, confidence - CATEGORY_CONFIDENCE_PENALTY)

            normalized_currency = item.currency.strip().upper()
            normalized_direction = item.direction.strip().lower()
            fingerprint = build_transaction_fingerprint(
                booking_date=item.booking_date,
                amount=item.amount,
                currency=normalized_currency,
                direction=normalized_direction,
                raw_description=item.raw_description,
                counterparty=item.counterparty,
            )
            duplicate_match = detect_duplicate_match(
                db=db,
                booking_date=item.booking_date,
                amount=item.amount,
                currency=normalized_currency,
                direction=normalized_direction,
                raw_description=item.raw_description,
                counterparty=item.counterparty,
                fingerprint=fingerprint,
            )

            if duplicate_match.status.value == DuplicateStatus.duplicate_confirmed.value:
                duplicate_transactions += 1
                continue

            tx = Transaction(
                import_job_id=job.id,
                booking_date=item.booking_date,
                amount=item.amount,
                currency=normalized_currency,
                direction=normalized_direction,
                counterparty=item.counterparty,
                raw_description=item.raw_description,
                normalized_description=_resolve_normalized_description(
                    raw_description=item.raw_description,
                    llm_normalized_description=item.normalized_description,
                ),
                category_id=category_id,
                confidence=confidence,
                duplicate_status=duplicate_match.status.value,
                duplicate_of_transaction_id=duplicate_match.duplicate_of_transaction_id,
                duplicate_reason=duplicate_match.duplicate_reason,
                duplicate_score=duplicate_match.duplicate_score,
                fingerprint=fingerprint,
            )
            db.add(tx)
            db.flush()

            if duplicate_match.status.value == DuplicateStatus.unique.value:
                new_transactions += 1
            elif duplicate_match.status.value == DuplicateStatus.possible_duplicate.value:
                needs_review_count += 1

        job.new_transactions = new_transactions
        job.duplicate_transactions = duplicate_transactions
        job.needs_review_count = needs_review_count
        job.status = "needs_review" if needs_review_count > 0 else "done"
        db.commit()

        return {
            "import_job_id": job.id,
            "transactions_count": len(parsed.transactions),
            "new_transactions": new_transactions,
            "duplicate_transactions": duplicate_transactions,
            "needs_review_count": needs_review_count,
        }

    except LLMClientError as e:
        db.rollback()
        job.status = "llm_failed"
        db.add(job)
        db.commit()
        raise HTTPException(status_code=502, detail=str(e)) from e

    except Exception as e:
        db.rollback()
        job.status = "failed"
        db.add(job)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Import failed: {e}") from e