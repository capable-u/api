from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.db import Base, engine
from app.api.routes_upload import router as upload_router
from app.api.routes_transactions import router as transactions_router

Base.metadata.create_all(bind=engine)

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


@app.get("/health")
def health():
    return {"status": "ok"}