from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import String, Date, DateTime, Numeric, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    import_job_id: Mapped[int] = mapped_column(ForeignKey("import_jobs.id"), index=True)

    booking_date: Mapped[date] = mapped_column(Date)
    value_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(10), default="EUR")

    direction: Mapped[str] = mapped_column(String(10))  # income / expense
    counterparty: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_description: Mapped[str] = mapped_column(Text)

    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)