import time
import logging
import threading
from app.db.session import SessionLocal
from app.services.ingest_service import run_ingest
from app.core.config import settings

logger = logging.getLogger(__name__)


def _is_invalid_grant_error(error: Exception) -> bool:
    message = str(error).lower()
    return "invalid_grant" in message or "expired or revoked" in message

def _auto_ingest_loop():
    logger.info("Auto-ingest background task started.")
    time.sleep(5)  # Wait briefly exactly once at the beginning
    while settings.auto_ingest_enabled:
        try:
            with SessionLocal() as db:
                result = run_ingest(db, max_files=settings.ingest_default_limit)
                
                processed = result.get("processed", 0)
                attempted = result.get("attempted", 0)
                skipped = result.get("skipped", 0)
                
                if attempted > 0 or skipped > 0:
                    logger.info(f"Auto-ingest batch complete: processed={processed}, attempted={attempted}, skipped={skipped}")
                
            # Wait for next interval
            time.sleep(settings.auto_ingest_interval_seconds)
            
        except Exception as e:
            if _is_invalid_grant_error(e):
                logger.error(
                    "Auto-ingest stopped: Google refresh token is invalid or revoked. "
                    "Update GOOGLE_REFRESH_TOKEN and restart backend."
                )
                break
            logger.error(f"Auto-ingest encountered an error: {e}")
            time.sleep(settings.auto_ingest_interval_seconds)

def start_auto_ingest_thread():
    if not settings.auto_ingest_enabled:
        return
    thread = threading.Thread(target=_auto_ingest_loop, daemon=True)
    thread.start()
