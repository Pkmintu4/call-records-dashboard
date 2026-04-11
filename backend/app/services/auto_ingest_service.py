import time
import logging
import threading
from app.db.session import SessionLocal
from app.services.ingest_lock import INGEST_LOCK
from app.services.ingest_service import run_ingest
from app.services.ingest_status import begin_ingest, fail_ingest, finish_ingest
from app.services.transcribe_service import SpeechApiDisabledError, TranscriptionConfigurationError
from app.core.config import settings

logger = logging.getLogger(__name__)


def _is_invalid_grant_error(error: Exception) -> bool:
    message = str(error).lower()
    return "invalid_grant" in message or "expired or revoked" in message

def _auto_ingest_loop():
    logger.info("Auto-ingest background task started.")
    time.sleep(5)  # Wait briefly exactly once at the beginning
    while settings.auto_ingest_enabled:
        lock_acquired = INGEST_LOCK.acquire(blocking=False)
        if not lock_acquired:
            logger.info("Skipping auto-ingest cycle: another ingest run is in progress.")
            time.sleep(settings.auto_ingest_interval_seconds)
            continue

        try:
            begin_ingest(mode="auto", folder=None, limit=settings.ingest_default_limit)
            with SessionLocal() as db:
                result = run_ingest(
                    db,
                    max_files=settings.ingest_default_limit,
                    audio_only=settings.ingest_force_audio_only,
                )
                finish_ingest(result)
                
                processed = result.get("processed", 0)
                attempted = result.get("attempted", 0)
                skipped = result.get("skipped", 0)
                
                if attempted > 0 or skipped > 0:
                    logger.info(f"Auto-ingest batch complete: processed={processed}, attempted={attempted}, skipped={skipped}")
                
            # Wait for next interval
            time.sleep(settings.auto_ingest_interval_seconds)
            
        except Exception as e:
            fail_ingest(str(e))
            if isinstance(e, TranscriptionConfigurationError):
                logger.error(
                    "Auto-ingest stopped: transcription provider is misconfigured. "
                    "Set required API key/env vars or switch transcription provider, then restart backend."
                )
                break
            if isinstance(e, SpeechApiDisabledError):
                logger.error(
                    "Auto-ingest stopped: Google Speech-to-Text API is disabled for this project. "
                    "Enable speech.googleapis.com, wait for propagation, then restart backend."
                )
                break
            if _is_invalid_grant_error(e):
                logger.error(
                    "Auto-ingest stopped: Google auth grant is invalid. "
                    "Update GOOGLE_REFRESH_TOKEN (OAuth mode) or verify service-account settings, "
                    "then restart backend."
                )
                break
            logger.error(f"Auto-ingest encountered an error: {e}")
            time.sleep(settings.auto_ingest_interval_seconds)
        finally:
            INGEST_LOCK.release()

def start_auto_ingest_thread():
    if not settings.auto_ingest_enabled:
        return
    thread = threading.Thread(target=_auto_ingest_loop, daemon=True)
    thread.start()
