from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import threading
from typing import Any


_STATE_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_progress() -> dict[str, Any]:
    return {
        "processed": 0,
        "reprocessed": 0,
        "attempted": 0,
        "examined": 0,
        "skipped_total": 0,
        "skipped_duplicate": 0,
        "skipped_non_transcript": 0,
        "skipped_too_short": 0,
        "skipped_unsupported_language": 0,
        "skipped_audio_too_large": 0,
        "skipped_audio_unsupported": 0,
        "skipped_empty": 0,
        "failed_transcription": 0,
        "failed_analysis": 0,
        "total_seen": 0,
        "audio_seen": 0,
        "text_seen": 0,
        "folder_id": "",
    }


_STATE: dict[str, Any] = {
    "running": False,
    "mode": "manual",
    "started_at": None,
    "updated_at": None,
    "limit": None,
    "folder": "",
    "current": _default_progress(),
    "last_result": None,
    "last_error": "",
}


def begin_ingest(mode: str, folder: str | None, limit: int | None) -> None:
    with _STATE_LOCK:
        _STATE["running"] = True
        _STATE["mode"] = mode
        _STATE["started_at"] = _now_iso()
        _STATE["updated_at"] = _STATE["started_at"]
        _STATE["limit"] = limit
        _STATE["folder"] = (folder or "").strip()
        _STATE["current"] = _default_progress()
        _STATE["last_error"] = ""


def update_ingest_progress(**kwargs: Any) -> None:
    with _STATE_LOCK:
        current = _STATE.get("current")
        if not isinstance(current, dict):
            current = _default_progress()
            _STATE["current"] = current

        for key, value in kwargs.items():
            if value is not None:
                current[key] = value

        _STATE["updated_at"] = _now_iso()


def finish_ingest(result: dict[str, Any]) -> None:
    with _STATE_LOCK:
        _STATE["running"] = False
        _STATE["updated_at"] = _now_iso()
        _STATE["last_result"] = deepcopy(result)
        _STATE["last_error"] = ""
        _STATE["current"] = {
            **_default_progress(),
            **{key: value for key, value in result.items() if key in _default_progress()},
        }


def fail_ingest(error_message: str) -> None:
    with _STATE_LOCK:
        _STATE["running"] = False
        _STATE["updated_at"] = _now_iso()
        _STATE["last_error"] = (error_message or "").strip()


def get_ingest_status() -> dict[str, Any]:
    with _STATE_LOCK:
        return deepcopy(_STATE)
