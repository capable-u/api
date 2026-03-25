from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.config import settings
from app.models.import_job import ImportJob
from app.models.transaction import Transaction
from app.services.pdf_extract import extract_text_with_pypdf
from app.services.transaction_parser import parse_transactions_from_text
from app.services.llm_client import LLMClientError

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("")
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
        raw_text = extract_text_with_pypdf(str(file_path))
        job.raw_text = raw_text
        job.status = "parsed_text"
        db.commit()

        parsed = await parse_transactions_from_text(raw_text)

        for item in parsed.transactions:
            tx = Transaction(
                import_job_id=job.id,
                booking_date=item.booking_date,
                value_date=item.value_date,
                amount=item.amount,
                currency=item.currency,
                direction=item.direction,
                counterparty=item.counterparty,
                raw_description=item.raw_description,
                category=item.category,
                confidence=item.confidence,
            )
            db.add(tx)

        job.status = "done"
        db.commit()

        return {
            "import_job_id": job.id,
            "transactions_count": len(parsed.transactions),
        }

    except LLMClientError as e:
        job.status = "llm_failed"
        db.commit()
        raise HTTPException(status_code=502, detail=str(e)) from e

    except Exception as e:
        job.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Import failed: {e}") from e