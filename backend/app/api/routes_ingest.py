from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.ingest_service import run_ingest


router = APIRouter()


@router.post("/run")
def ingest_now(
    folder: str | None = Query(default=None, description="Google Drive folder ID or folder URL"),
    limit: int = Query(default=settings.ingest_default_limit, ge=1, le=500, description="Maximum transcript files to process in this run"),
    db: Session = Depends(get_db),
) -> dict[str, int | str]:
    try:
        return run_ingest(db, folder_input=folder, max_files=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
