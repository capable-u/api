"""add amount_base to transactions and consolidate monthly summary by base currency

Revision ID: b4c6d8e0f2a4
Revises: a3b5c7d9e1f2
Create Date: 2026-04-22 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b4c6d8e0f2a4"
down_revision: Union[str, Sequence[str], None] = "a3b5c7d9e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("amount_base", sa.Numeric(12, 2), nullable=True),
    )

    # Clear summary tables before changing unique constraints — they will be
    # rebuilt by the application after exchange rates are populated.
    op.execute("DELETE FROM monthly_category_summary")
    op.execute("DELETE FROM monthly_summary")

    # monthly_summary: drop (month, currency) → replace with (month) only
    op.drop_constraint("uq_monthly_summary_month", "monthly_summary", type_="unique")
    op.create_unique_constraint(
        "uq_monthly_summary_month", "monthly_summary", ["month"]
    )

    # monthly_category_summary: drop (month, category_id, currency) → (month, category_id)
    op.drop_constraint(
        "uq_monthly_category_summary_month", "monthly_category_summary", type_="unique"
    )
    op.create_unique_constraint(
        "uq_monthly_category_summary_month",
        "monthly_category_summary",
        ["month", "category_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_monthly_category_summary_month", "monthly_category_summary", type_="unique"
    )
    op.create_unique_constraint(
        "uq_monthly_category_summary_month",
        "monthly_category_summary",
        ["month", "category_id", "currency"],
    )

    op.drop_constraint("uq_monthly_summary_month", "monthly_summary", type_="unique")
    op.create_unique_constraint(
        "uq_monthly_summary_month", "monthly_summary", ["month", "currency"]
    )

    op.drop_column("transactions", "amount_base")
