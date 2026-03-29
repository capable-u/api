from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_upload import router as upload_router
from app.api.routes_transactions import router as transactions_router
from app.api.routes_categories import router as categories_router
from app.schemas.common import HealthResponse


app = FastAPI(title="Budget MVP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router)
app.include_router(transactions_router)
app.include_router(categories_router)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return {"status": "ok"}