import asyncio
import logging

from app.worker.celery_app import celery_app
from app.core.db import SessionLocal
from app.models.import_job import ImportJob
from app.services.exchange_rate_service import update_exchange_rates
from app.services.import_pipeline import ingest_transactions, load_categories
from app.services.llm_client import LLMClientError
from app.services.pdf_extract import extract_text_with_pypdf
from app.services.transaction_parser import parse_transactions_from_text

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.worker.tasks.process_import_job")
def process_import_job(self, import_job_id: int, file_path: str) -> dict:
    db = SessionLocal()
    try:
        job = db.get(ImportJob, import_job_id)
        if job is None:
            logger.error("ImportJob %s not found", import_job_id)
            return {"status": "not_found"}

        try:
            categories, valid_category_ids, other_category = load_categories(db)
            category_pairs = [(item.id, item.name) for item in categories]

            raw_text = extract_text_with_pypdf(file_path)
            job.raw_text = raw_text
            job.status = "parsed_text"
            db.commit()

            parsed = asyncio.run(
                parse_transactions_from_text(raw_text, categories=category_pairs)
            )
            job.status = "parsed_transactions"
            new_transactions, duplicate_transactions, needs_review_count = (
                ingest_transactions(
                    db=db,
                    job=job,
                    transactions=parsed.transactions,
                    valid_category_ids=valid_category_ids,
                    other_category=other_category,
                )
            )
            db.commit()

            return {
                "import_job_id": job.id,
                "new_transactions": new_transactions,
                "duplicate_transactions": duplicate_transactions,
                "needs_review_count": needs_review_count,
            }

        except LLMClientError as e:
            db.rollback()
            job.status = "llm_failed"
            db.add(job)
            db.commit()
            logger.error("LLM error for job %s: %s", import_job_id, e)
            raise

        except Exception as e:
            db.rollback()
            job.status = "failed"
            db.add(job)
            db.commit()
            logger.error("Pipeline error for job %s: %s", import_job_id, e)
            raise

    finally:
        db.close()


@celery_app.task(name="app.worker.tasks.refresh_exchange_rates")
def refresh_exchange_rates() -> dict:
    db = SessionLocal()
    try:
        count = update_exchange_rates(db)
        logger.info("Exchange rates refreshed: %s rows", count)
        return {"updated": count}
    except Exception as e:
        logger.error("Exchange rate refresh failed: %s", e)
        raise
    finally:
        db.close()
