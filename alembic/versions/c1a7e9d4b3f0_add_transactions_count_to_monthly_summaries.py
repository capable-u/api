"""add transactions_count to monthly summaries

Revision ID: c1a7e9d4b3f0
Revises: 9c0d8f2b4a1e
Create Date: 2026-04-09 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1a7e9d4b3f0"
down_revision: Union[str, Sequence[str], None] = "9c0d8f2b4a1e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "monthly_summary",
        sa.Column(
            "transactions_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "monthly_category_summary",
        sa.Column(
            "transactions_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("monthly_category_summary", "transactions_count")
    op.drop_column("monthly_summary", "transactions_count")
