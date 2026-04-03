"""add monthly summary tables

Revision ID: 8b1f6e4a92cd
Revises: 4f2a6c1d9eaa
Create Date: 2026-04-01 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8b1f6e4a92cd"
down_revision: Union[str, Sequence[str], None] = "4f2a6c1d9eaa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "monthly_summary",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("income_total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("expense_total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_monthly_summary")),
        sa.UniqueConstraint("month", "currency", name=op.f("uq_monthly_summary_month")),
    )
    op.create_index(
        op.f("ix_monthly_summary_month"), "monthly_summary", ["month"], unique=False
    )

    op.create_table(
        "monthly_category_summary",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("income_total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("expense_total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_monthly_category_summary_category_id_categories"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_monthly_category_summary")),
        sa.UniqueConstraint(
            "month",
            "category_id",
            "currency",
            name=op.f("uq_monthly_category_summary_month"),
        ),
    )
    op.create_index(
        op.f("ix_monthly_category_summary_category_id"),
        "monthly_category_summary",
        ["category_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_monthly_category_summary_month"),
        "monthly_category_summary",
        ["month"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_monthly_category_summary_month"), table_name="monthly_category_summary"
    )
    op.drop_index(
        op.f("ix_monthly_category_summary_category_id"),
        table_name="monthly_category_summary",
    )
    op.drop_table("monthly_category_summary")

    op.drop_index(op.f("ix_monthly_summary_month"), table_name="monthly_summary")
    op.drop_table("monthly_summary")
