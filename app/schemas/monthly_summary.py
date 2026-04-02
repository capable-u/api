from datetime import date

from pydantic import BaseModel


class MonthlySummaryRowResponse(BaseModel):
    month: date
    currency: str
    income_total: float
    expense_total: float


class MonthlyCategorySummaryRowResponse(BaseModel):
    month: date
    currency: str
    category_id: int
    income_total: float
    expense_total: float


class MonthlyOverviewResponse(BaseModel):
    month_from: date | None = None
    month_to: date | None = None
    currency: str | None = None
    summaries: list[MonthlySummaryRowResponse]
    category_summaries: list[MonthlyCategorySummaryRowResponse]

