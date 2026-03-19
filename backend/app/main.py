from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_dashboard import router as dashboard_router
from app.api.routes_google_auth import router as google_auth_router
from app.api.routes_ingest import router as ingest_router
from app.core.config import settings
from app.db.base import Base
from app.db.schema_sync import ensure_sentiment_summary_column
from app.db.session import engine


app = FastAPI(title="Call Records Sentiment API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_sentiment_summary_column(engine)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(ingest_router, prefix="/api/ingest", tags=["ingest"])
app.include_router(dashboard_router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(google_auth_router, prefix="/api/google", tags=["google-auth"])
