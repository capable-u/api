import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.exchange_rate_service import update_exchange_rates

router = APIRouter(prefix="/exchange-rates", tags=["exchange-rates"])


class UpdateRatesResponse(BaseModel):
    updated: int


@router.post("/update", response_model=UpdateRatesResponse)
def update_rates(db: Session = Depends(get_db)):
    try:
        count = update_exchange_rates(db)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Frankfurter API error: {exc.response.status_code}",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to reach Frankfurter API: {exc}",
        ) from exc
    return {"updated": count}
