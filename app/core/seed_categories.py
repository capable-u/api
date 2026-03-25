from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.category import Category


DEFAULT_CATEGORIES = [
    {"slug": "salary", "name": "Salary"},
    {"slug": "rent", "name": "Rent"},
    {"slug": "groceries", "name": "Groceries"},
    {"slug": "transport", "name": "Transport"},
    {"slug": "utilities", "name": "Utilities"},
    {"slug": "insurance", "name": "Insurance"},
    {"slug": "health", "name": "Health"},
    {"slug": "shopping", "name": "Shopping"},
    {"slug": "subscriptions", "name": "Subscriptions"},
    {"slug": "restaurants", "name": "Restaurants"},
    {"slug": "entertainment", "name": "Entertainment"},
    {"slug": "transfer", "name": "Transfer"},
    {"slug": "cash_withdrawal", "name": "Cash Withdrawal"},
    {"slug": "tax", "name": "Tax"},
    {"slug": "other", "name": "Other"},
]


def seed_categories() -> None:
    with SessionLocal() as db:
        existing_slugs = set(
            db.execute(select(Category.slug)).scalars().all()
        )

        to_create = [
            Category(slug=item["slug"], name=item["name"])
            for item in DEFAULT_CATEGORIES
            if item["slug"] not in existing_slugs
        ]

        if to_create:
            db.add_all(to_create)
            db.commit()


if __name__ == "__main__":
    seed_categories()