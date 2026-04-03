"""add color and updated_at to categories

Revision ID: 9c0d8f2b4a1e
Revises: 8b1f6e4a92cd
Create Date: 2026-04-03 12:00:00.000000

"""

from datetime import datetime, timezone
import random
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9c0d8f2b4a1e"
down_revision: Union[str, Sequence[str], None] = "8b1f6e4a92cd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _random_hex_color() -> str:
    return f"#{random.randint(0, 0xFFFFFF):06X}"


def upgrade() -> None:
    op.add_column("categories", sa.Column("color", sa.String(length=7), nullable=True))
    op.add_column("categories", sa.Column("updated_at", sa.DateTime(), nullable=True))

    bind = op.get_bind()
    categories_table = sa.table(
        "categories",
        sa.column("id", sa.Integer()),
        sa.column("created_at", sa.DateTime()),
        sa.column("color", sa.String(length=7)),
        sa.column("updated_at", sa.DateTime()),
    )
    rows = bind.execute(
        sa.select(categories_table.c.id, categories_table.c.created_at)
    ).all()

    for row in rows:
        bind.execute(
            sa.update(categories_table)
            .where(categories_table.c.id == row.id)
            .values(
                color=_random_hex_color(),
                updated_at=row.created_at
                or datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )

    op.alter_column("categories", "color", nullable=False)
    op.alter_column("categories", "updated_at", nullable=False)


def downgrade() -> None:
    op.drop_column("categories", "updated_at")
    op.drop_column("categories", "color")
