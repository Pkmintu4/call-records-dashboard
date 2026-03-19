import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.drive_client import download_text_file, list_txt_files, resolve_folder_id_from_path
from app.integrations.drive_path import resolve_drive_folder_id
from app.integrations.google_oauth import get_google_access_token
from app.models.sentiment import Sentiment
from app.models.transcript import Transcript
from app.services.sentiment_service import analyze_sentiment


def run_ingest(
    db: Session,
    folder_input: str | None = None,
    max_files: int | None = None,
) -> dict[str, int | str]:
    access_token = get_google_access_token()
    resolved_folder_id = ""
    if folder_input:
        normalized = folder_input.strip()
        if "/" in normalized and "drive.google.com" not in normalized and not normalized.startswith("http"):
            resolved_folder_id = resolve_folder_id_from_path(access_token, normalized)
        else:
            resolved_folder_id = resolve_drive_folder_id(normalized)

    drive_files = list_txt_files(access_token, folder_id=resolved_folder_id or None)

    created = 0
    skipped = 0
    skipped_non_transcript = 0
    skipped_too_short = 0
    attempted = 0

    for drive_file in drive_files:
        if max_files is not None and max_files > 0 and attempted >= max_files:
            break

        file_name_lower = drive_file.name.lower()
        if "transcript" not in file_name_lower or not file_name_lower.endswith(".txt"):
            skipped_non_transcript += 1
            continue

        existing = db.scalar(select(Transcript).where(Transcript.drive_file_id == drive_file.file_id))
        if existing:
            skipped += 1
            continue

        content = download_text_file(access_token, drive_file.file_id)
        normalized_content = content.strip()
        if not normalized_content:
            skipped += 1
            continue

        if len(normalized_content) < settings.transcript_min_chars:
            skipped_too_short += 1
            continue

        attempted += 1

        transcript = Transcript(
            drive_file_id=drive_file.file_id,
            file_name=drive_file.name,
            modified_time=drive_file.modified_time,
            content=normalized_content,
        )
        db.add(transcript)
        db.flush()

        score, label, explanation, kpis = analyze_sentiment(normalized_content)
        kpis["call_id"] = str(transcript.id)
        sentiment = Sentiment(
            transcript_id=transcript.id,
            score=score,
            label=label,
            summary=explanation,
            kpi_json=json.dumps(kpis, ensure_ascii=False),
            explanation=explanation,
            keywords=", ".join(kpis.get("parent_concerns", [])),
        )
        db.add(sentiment)
        created += 1

    db.commit()
    return {
        "processed": created,
        "skipped": skipped,
        "skipped_non_transcript": skipped_non_transcript,
        "skipped_too_short": skipped_too_short,
        "total_seen": len(drive_files),
        "attempted": attempted,
        "folder_id": resolved_folder_id,
    }
