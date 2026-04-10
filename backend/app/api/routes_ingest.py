from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.ingest_lock import INGEST_LOCK
from app.services.ingest_service import run_ingest
from app.services.ingest_status import begin_ingest, fail_ingest, finish_ingest, get_ingest_status
from app.services.transcribe_service import SpeechApiDisabledError, TranscriptionConfigurationError


router = APIRouter()


@router.get("/status")
def ingest_status() -> dict[str, object]:
    return get_ingest_status()


@router.post("/run")
def ingest_now(
    folder: str | None = Query(default=None, description="Google Drive folder ID or folder URL"),
    limit: int = Query(default=settings.ingest_default_limit, ge=1, le=500, description="Maximum transcript files to process in this run"),
    force_reprocess: bool = Query(default=False, description="Re-analyze already ingested files instead of skipping duplicates"),
    audio_only: bool = Query(default=False, description="Process only supported audio files and skip .txt transcript files"),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    if not INGEST_LOCK.acquire(blocking=False):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Ingest is already running. Please retry in a moment.",
                "status": get_ingest_status(),
            },
        )

    begin_ingest(mode="manual", folder=folder, limit=limit)

    try:
        result = run_ingest(
            db,
            folder_input=folder,
            max_files=limit,
            force_reprocess=force_reprocess,
            audio_only=audio_only,
        )
        finish_ingest(result)
        return result
    except SpeechApiDisabledError as exc:
        db.rollback()
        fail_ingest(str(exc))
        raise HTTPException(
            status_code=503,
            detail={
                "message": str(exc),
                "action": "Enable speech.googleapis.com in Google Cloud Console, wait a few minutes, and retry ingest.",
            },
        ) from exc
    except TranscriptionConfigurationError as exc:
        db.rollback()
        fail_ingest(str(exc))
        raise HTTPException(
            status_code=503,
            detail={
                "message": str(exc),
                "action": "Fix transcription provider setup (API key, model availability, and Gemini quota/billing) or switch TRANSCRIPTION_PROVIDER=google_speech.",
            },
        ) from exc
    except Exception as exc:
        db.rollback()
        fail_ingest(str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        INGEST_LOCK.release()
