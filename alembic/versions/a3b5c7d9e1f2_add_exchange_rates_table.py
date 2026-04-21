"""add exchange_rates table

Revision ID: a3b5c7d9e1f2
Revises: c1a7e9d4b3f0
Create Date: 2026-04-22 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3b5c7d9e1f2"
down_revision: Union[str, Sequence[str], None] = "c1a7e9d4b3f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exchange_rates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("base_currency", sa.String(10), nullable=False),
        sa.Column("target_currency", sa.String(10), nullable=False),
        sa.Column("rate", sa.Numeric(18, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exchange_rates")),
        sa.UniqueConstraint(
            "date",
            "base_currency",
            "target_currency",
            name="uq_exchange_rates_date_base_target",
        ),
    )
    op.create_index(op.f("ix_exchange_rates_date"), "exchange_rates", ["date"])


def downgrade() -> None:
    op.drop_index(op.f("ix_exchange_rates_date"), table_name="exchange_rates")
    op.drop_table("exchange_rates")
