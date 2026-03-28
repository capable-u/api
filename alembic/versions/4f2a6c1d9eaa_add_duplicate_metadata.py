"""add duplicate metadata

Revision ID: 4f2a6c1d9eaa
Revises: 3d50bdd9ecd2
Create Date: 2026-03-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4f2a6c1d9eaa"
down_revision: Union[str, Sequence[str], None] = "3d50bdd9ecd2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("duplicate_of_transaction_id", sa.Integer(), nullable=True))
    op.add_column("transactions", sa.Column("duplicate_reason", sa.String(length=50), nullable=True))
    op.add_column("transactions", sa.Column("duplicate_score", sa.Numeric(precision=4, scale=3), nullable=True))

    op.create_foreign_key(
        op.f("fk_transactions_duplicate_of_transaction_id_transactions"),
        "transactions",
        "transactions",
        ["duplicate_of_transaction_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        op.f("ix_transactions_duplicate_of_transaction_id"),
        "transactions",
        ["duplicate_of_transaction_id"],
        unique=False,
    )

    op.create_index(
        "ix_transactions_probable_lookup",
        "transactions",
        ["amount", "currency", "direction", "booking_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_probable_lookup", table_name="transactions")
    op.drop_index(op.f("ix_transactions_duplicate_of_transaction_id"), table_name="transactions")
    op.drop_constraint(
        op.f("fk_transactions_duplicate_of_transaction_id_transactions"),
        "transactions",
        type_="foreignkey",
    )
    op.drop_column("transactions", "duplicate_score")
    op.drop_column("transactions", "duplicate_reason")
    op.drop_column("transactions", "duplicate_of_transaction_id")

