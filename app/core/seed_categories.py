from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.category import Category


DEFAULT_CATEGORIES = [
    "Salary",
    "Rent",
    "Groceries",
    "Transport",
    "Utilities",
    "Insurance",
    "Health",
    "Shopping",
    "Subscriptions",
    "Restaurants",
    "Entertainment",
    "Transfer",
    "Cash Withdrawal",
    "Tax",
    "Other",
]


def seed_categories() -> None:
    with SessionLocal() as db:
        existing_names = set(db.execute(select(Category.name)).scalars().all())

        to_create = [
            Category(name=name)
            for name in DEFAULT_CATEGORIES
            if name not in existing_names
        ]

        if to_create:
            db.add_all(to_create)
            db.commit()


if __name__ == "__main__":
    seed_categories()