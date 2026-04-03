from datetime import datetime

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timezone import UTCDateTime, utc_now
from app.models.base import Base


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    total_transactions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_transactions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_transactions: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    needs_review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )
