from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.category import Category
from app.schemas.category import CategoryResponse

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryResponse])
def list_categories(db: Session = Depends(get_db)):
    items = db.execute(select(Category).order_by(Category.name.asc())).scalars().all()

    return [
        {
            "id": item.id,
            "name": item.name,
        }
        for item in items
    ]