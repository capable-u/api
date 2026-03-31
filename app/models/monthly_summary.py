from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MonthlySummary(Base):
    __tablename__ = "monthly_summary"
    __table_args__ = (UniqueConstraint("month", "currency"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    month: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="EUR", nullable=False)

    income_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    expense_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

