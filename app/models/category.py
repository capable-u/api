from datetime import datetime
import random

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timezone import UTCDateTime, utc_now
from app.models.base import Base


def _random_hex_color() -> str:
    return f"#{random.randint(0, 0xFFFFFF):06X}"


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    color: Mapped[str] = mapped_column(
        String(7), nullable=False, default=_random_hex_color
    )

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )
