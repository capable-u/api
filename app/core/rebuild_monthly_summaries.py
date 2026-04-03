from sqlalchemy import inspect

from app.core.db import SessionLocal
from app.models.monthly_category_summary import MonthlyCategorySummary
from app.models.monthly_summary import MonthlySummary
from app.services.monthly_summary_service import rebuild_all_monthly_summaries


def rebuild_monthly_summaries() -> None:
    with SessionLocal() as db:
        inspector = inspect(db.get_bind())
        if not inspector.has_table(
            MonthlySummary.__tablename__
        ) or not inspector.has_table(MonthlyCategorySummary.__tablename__):
            return

        rebuild_all_monthly_summaries(db)
        db.commit()


if __name__ == "__main__":
    rebuild_monthly_summaries()
