from datetime import date

from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session

from app.models.enums import Direction, DuplicateStatus
from app.models.monthly_category_summary import MonthlyCategorySummary
from app.models.monthly_summary import MonthlySummary
from app.models.transaction import Transaction


def month_start(value: date) -> date:
    return value.replace(day=1)


def next_month_start(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def rebuild_monthly_summaries_for_month(db: Session, month: date) -> None:
    normalized_month = month_start(month)
    month_end = next_month_start(normalized_month)

    db.execute(delete(MonthlySummary).where(MonthlySummary.month == normalized_month))
    db.execute(delete(MonthlyCategorySummary).where(MonthlyCategorySummary.month == normalized_month))

    base_filters = [
        Transaction.booking_date >= normalized_month,
        Transaction.booking_date < month_end,
        Transaction.duplicate_status == DuplicateStatus.unique.value,
    ]

    income_total = func.coalesce(
        func.sum(
            case(
                (Transaction.direction == Direction.income.value, Transaction.amount),
                else_=0,
            )
        ),
        0,
    )
    expense_total = func.coalesce(
        func.sum(
            case(
                (Transaction.direction == Direction.expense.value, Transaction.amount),
                else_=0,
            )
        ),
        0,
    )

    monthly_rows = db.execute(
        select(
            Transaction.currency,
            income_total.label("income_total"),
            expense_total.label("expense_total"),
        )
        .where(*base_filters)
        .group_by(Transaction.currency)
    ).all()

    if monthly_rows:
        db.add_all(
            [
                MonthlySummary(
                    month=normalized_month,
                    currency=row.currency,
                    income_total=row.income_total,
                    expense_total=row.expense_total,
                )
                for row in monthly_rows
            ]
        )

    category_income_total = func.coalesce(
        func.sum(
            case(
                (Transaction.direction == Direction.income.value, Transaction.amount),
                else_=0,
            )
        ),
        0,
    )
    category_expense_total = func.coalesce(
        func.sum(
            case(
                (Transaction.direction == Direction.expense.value, Transaction.amount),
                else_=0,
            )
        ),
        0,
    )

    category_rows = db.execute(
        select(
            Transaction.category_id,
            Transaction.currency,
            category_income_total.label("income_total"),
            category_expense_total.label("expense_total"),
        )
        .where(
            *base_filters,
            Transaction.category_id.is_not(None),
        )
        .group_by(Transaction.category_id, Transaction.currency)
    ).all()

    if category_rows:
        db.add_all(
            [
                MonthlyCategorySummary(
                    month=normalized_month,
                    category_id=row.category_id,
                    currency=row.currency,
                    income_total=row.income_total,
                    expense_total=row.expense_total,
                )
                for row in category_rows
            ]
        )


def rebuild_monthly_summaries_for_months(db: Session, months: set[date]) -> None:
    for month in sorted({month_start(item) for item in months}):
        rebuild_monthly_summaries_for_month(db=db, month=month)


def rebuild_all_monthly_summaries(db: Session) -> None:
    months = set(db.execute(select(Transaction.booking_date).distinct()).scalars().all())
    rebuild_monthly_summaries_for_months(db=db, months=months)

