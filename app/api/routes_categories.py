from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.category import Category
from app.schemas.category import (
    CategoryCreateRequest,
    CategoryResponse,
    CategoryUpdateRequest,
    DeleteCategoryResponse,
)
from app.schemas.common import ErrorResponse

router = APIRouter(prefix="/categories", tags=["categories"])
SYSTEM_OTHER_NAME = "other"


def _is_system_other(category: Category) -> bool:
    return category.name.strip().lower() == SYSTEM_OTHER_NAME


def _find_category_by_name_ci(
    db: Session, normalized_name: str, exclude_id: int | None = None
) -> Category | None:
    query = select(Category).where(func.lower(Category.name) == normalized_name.lower())
    if exclude_id is not None:
        query = query.where(Category.id != exclude_id)
    return db.execute(query.limit(1)).scalar_one_or_none()


def _serialize_category(item: Category) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "color": item.color,
        "updated_at": item.updated_at,
    }


@router.get("", response_model=list[CategoryResponse])
def list_categories(db: Session = Depends(get_db)):
    items = db.execute(select(Category).order_by(Category.name.asc())).scalars().all()

    return [_serialize_category(item) for item in items]


@router.post(
    "",
    response_model=CategoryResponse,
    responses={409: {"model": ErrorResponse}},
)
def create_category(
    payload: CategoryCreateRequest,
    db: Session = Depends(get_db),
):
    normalized_name = payload.name.strip()
    if not normalized_name:
        raise HTTPException(status_code=400, detail="Category name cannot be empty")

    existing = _find_category_by_name_ci(db=db, normalized_name=normalized_name)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Category name already exists")

    category = Category(name=normalized_name)
    if payload.color is not None:
        category.color = payload.color.upper()

    db.add(category)
    db.commit()
    db.refresh(category)
    return _serialize_category(category)


@router.patch(
    "/{category_id}",
    response_model=CategoryResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def update_category(
    category_id: int,
    payload: CategoryUpdateRequest,
    db: Session = Depends(get_db),
):
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    if _is_system_other(category):
        raise HTTPException(
            status_code=400,
            detail='System category "Other" cannot be modified',
        )

    update_data = payload.model_dump(exclude_unset=True)

    if "name" in update_data and update_data["name"] is not None:
        normalized_name = update_data["name"].strip()
        if not normalized_name:
            raise HTTPException(status_code=400, detail="Category name cannot be empty")
        existing = _find_category_by_name_ci(
            db=db, normalized_name=normalized_name, exclude_id=category.id
        )
        if existing is not None:
            raise HTTPException(status_code=409, detail="Category name already exists")
        category.name = normalized_name

    if "color" in update_data and update_data["color"] is not None:
        category.color = update_data["color"].upper()

    db.add(category)
    db.commit()

    db.refresh(category)
    return _serialize_category(category)


@router.delete(
    "/{category_id}",
    response_model=DeleteCategoryResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
):
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    if _is_system_other(category):
        raise HTTPException(
            status_code=400,
            detail='System category "Other" cannot be modified',
        )

    db.delete(category)
    db.commit()
    return {"id": category_id, "deleted": True}
