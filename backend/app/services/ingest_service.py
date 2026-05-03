import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.drive_client import (
    DriveFile,
    download_file_bytes,
    download_text_file,
    list_audio_files,
    list_txt_files,
    resolve_folder_id_from_path,
)
from app.integrations.drive_path import resolve_drive_folder_id
from app.integrations.google_oauth import CLOUD_PLATFORM_SCOPE, get_google_access_token
from app.models.sentiment import Sentiment
from app.models.transcript import Transcript
from app.services.intent_summary_service import classify_intent_summary
from app.services.ingest_status import update_ingest_progress
from app.services.sentiment_service import analyze_sentiment
from app.services.translate_service import translate_to_english
from app.services.transcribe_service import (
    SpeechApiDisabledError,
    TranscriptionConfigurationError,
    UnsupportedLanguageError,
    can_normalize_audio_locally,
    get_transcription_max_audio_bytes,
    is_audio_file,
    is_audio_transcription_supported,
    transcribe_audio_bytes,
    uses_google_speech_provider,
)


logger = logging.getLogger(__name__)
MAX_RESULT_TRANSCRIPT_PREVIEW_CHARS = 4000
MAX_RESULT_TRANSCRIPTS = 12


def _normalize_transcript_text(text: str) -> str:
    raw = str(text or "")
    if not raw.strip():
        return ""

    normalized_lines = [" ".join(line.split()) for line in raw.replace("\r\n", "\n").split("\n")]
    non_empty_lines = [line for line in normalized_lines if line]
    if non_empty_lines:
        return "\n".join(non_empty_lines)

    return " ".join(raw.split())


def _is_txt_transcript_file(file_name: str) -> bool:
    lower_name = file_name.lower()
    if not lower_name.endswith(".txt"):
        return False
    keyword = settings.transcript_filename_keyword.strip().lower()
    if not keyword:
        return True
    return keyword in lower_name


def _is_excluded_call_file_name(file_name: str | None) -> bool:
    normalized = str(file_name or "").strip().lower()
    return "(whatsapp)" in normalized


def _sorted_drive_files(items: list[DriveFile]) -> list[DriveFile]:
    return sorted(
        items,
        key=lambda item: item.modified_time.isoformat() if item.modified_time else "",
        reverse=True,
    )


def _truncate_preview(text: str, max_chars: int = MAX_RESULT_TRANSCRIPT_PREVIEW_CHARS) -> str:
    normalized = (text or "").strip()
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[:max_chars].rstrip()} ..."


def _is_audio_too_large_error(message: str) -> bool:
    normalized = (message or "").strip().lower()
    if not normalized:
        return False

    markers = (
        "exceeds active transcription payload limit",
        "normalized audio exceeds active transcription payload limit",
        "request payload size exceeds the limit",
        "inline audio exceeds duration limit",
        "audio exceeds gemini_transcription_inline_max_mb",
        "audio chunk exceeds active transcription payload limit",
        "unable to split audio into chunks",
    )
    return any(marker in normalized for marker in markers)


def _is_empty_transcript_error(message: str) -> bool:
    normalized = (message or "").strip().lower()
    if not normalized:
        return False
    return "no transcript" in normalized or "empty transcript" in normalized


def _is_db_connection_closed_error(message: str) -> bool:
    normalized = (message or "").strip().lower()
    if not normalized:
        return False

    markers = (
        "ssl connection has been closed unexpectedly",
        "server closed the connection unexpectedly",
        "connection not open",
        "closed unexpectedly",
        "connection already closed",
    )
    return any(marker in normalized for marker in markers)


def run_ingest(
    db: Session,
    folder_input: str | None = None,
    max_files: int | None = None,
    force_reprocess: bool = False,
    reprocess_ignore_only: bool = False,
    audio_only: bool = False,
) -> dict[str, object]:
    drive_access_token = get_google_access_token()
    speech_access_token: str | None = None
    use_google_speech = uses_google_speech_provider()
    resolved_folder_id = ""
    if folder_input:
        normalized = folder_input.strip()
        if "/" in normalized and "drive.google.com" not in normalized and not normalized.startswith("http"):
            try:
                resolved_folder_id = resolve_folder_id_from_path(drive_access_token, normalized)
            except ValueError as exc:
                # Colab-style paths (e.g. /content/drive/MyDrive/...) are not stable in
                # service-account mode; fall back to configured folder ID when available.
                if normalized.replace("\\", "/").startswith("/content/drive/") and settings.google_drive_folder_id:
                    logger.warning(
                        "Drive path '%s' could not be resolved (%s). Falling back to GOOGLE_DRIVE_FOLDER_ID.",
                        normalized,
                        exc,
                    )
                    resolved_folder_id = settings.google_drive_folder_id
                else:
                    raise ValueError(
                        "Folder path could not be resolved. Pass a Google Drive folder ID/URL "
                        "or leave folder empty to use GOOGLE_DRIVE_FOLDER_ID."
                    ) from exc
        else:
            resolved_folder_id = resolve_drive_folder_id(normalized)

    txt_files: list[DriveFile] = []
    if not audio_only:
        txt_files = list_txt_files(drive_access_token, folder_id=resolved_folder_id or None)

    audio_files: list[DriveFile] = []
    if settings.audio_ingest_enabled:
        audio_files = list_audio_files(drive_access_token, folder_id=resolved_folder_id or None)

    drive_files = _sorted_drive_files([*txt_files, *audio_files])

    created = 0
    skipped_duplicate = 0
    skipped_non_transcript = 0
    skipped_too_short = 0
    skipped_unsupported_language = 0
    skipped_audio_too_large = 0
    skipped_audio_unsupported = 0
    skipped_empty = 0
    skipped_reprocess_filter = 0
    failed_transcription = 0
    failed_analysis = 0
    attempted = 0
    examined = 0
    reprocessed = 0
    processed_records: list[dict[str, object]] = []
    transcription_max_audio_bytes = get_transcription_max_audio_bytes()
    can_normalize_audio = can_normalize_audio_locally()

    def _publish_progress() -> None:
        skipped_total = (
            skipped_duplicate
            + skipped_non_transcript
            + skipped_too_short
            + skipped_unsupported_language
            + skipped_audio_too_large
            + skipped_audio_unsupported
            + skipped_empty
            + skipped_reprocess_filter
        )
        update_ingest_progress(
            processed=created,
            reprocessed=reprocessed,
            attempted=attempted,
            examined=examined,
            skipped_total=skipped_total,
            skipped_duplicate=skipped_duplicate,
            skipped_non_transcript=skipped_non_transcript,
            skipped_too_short=skipped_too_short,
            skipped_unsupported_language=skipped_unsupported_language,
            skipped_audio_too_large=skipped_audio_too_large,
            skipped_audio_unsupported=skipped_audio_unsupported,
            skipped_empty=skipped_empty,
            skipped_reprocess_filter=skipped_reprocess_filter,
            failed_transcription=failed_transcription,
            failed_analysis=failed_analysis,
            total_seen=len(drive_files),
            audio_seen=len(audio_files),
            text_seen=len(txt_files),
            folder_id=resolved_folder_id,
        )

    _publish_progress()

    for drive_file in drive_files:
        if max_files is not None and max_files > 0 and created >= max_files:
            break

        if _is_excluded_call_file_name(drive_file.name):
            skipped_non_transcript += 1
            _publish_progress()
            continue

        source_is_text = _is_txt_transcript_file(drive_file.name)
        source_is_audio = is_audio_file(drive_file.name, drive_file.mime_type)
        if not source_is_text and not source_is_audio:
            skipped_non_transcript += 1
            _publish_progress()
            continue

        examined += 1
        _publish_progress()

        existing_transcript_id = db.scalar(
            select(Transcript.id).where(Transcript.drive_file_id == drive_file.file_id)
        )
        is_reprocess_target = existing_transcript_id is not None and force_reprocess
        if existing_transcript_id and not force_reprocess:
            skipped_duplicate += 1
            _publish_progress()
            continue

        if existing_transcript_id and force_reprocess and reprocess_ignore_only:
            existing_intent = db.scalar(
                select(Sentiment.intent_category).where(Sentiment.transcript_id == existing_transcript_id)
            )
            if str(existing_intent or "").strip().upper() != "IGNORE":
                skipped_reprocess_filter += 1
                _publish_progress()
                continue

        # Close read transaction before long external IO work (Drive + transcription)
        # to avoid idle-in-transaction SSL disconnects on managed Postgres.
        if db.in_transaction():
            db.rollback()

        if drive_file.size_bytes is not None and drive_file.size_bytes < settings.transcript_min_chars:
            skipped_too_short += 1
            _publish_progress()
            continue

        if source_is_audio and not is_audio_transcription_supported(drive_file.name, drive_file.mime_type):
            skipped_audio_unsupported += 1
            _publish_progress()
            continue

        # If ffmpeg normalization is unavailable, pre-check strict payload size.
        # With normalization available, allow larger source payloads because they may
        # compress under provider limits after conversion.
        if source_is_audio and drive_file.size_bytes is not None:
            if not can_normalize_audio and drive_file.size_bytes > transcription_max_audio_bytes:
                skipped_audio_too_large += 1
                _publish_progress()
                continue
            if can_normalize_audio and drive_file.size_bytes > (transcription_max_audio_bytes * 4):
                skipped_audio_too_large += 1
                _publish_progress()
                continue

        attempted += 1
        _publish_progress()

        source_type = "audio" if source_is_audio else "text"
        transcription_language: str | None = None
        duration_seconds: float | None = None
        transcription_provider: str | None = "text_upload" if source_is_text else None
        transcription_confidence: float | None = None
        transcription_rescue_used = False
        transcription_rescue_provider: str | None = None
        transcription_rescue_reason: str | None = None

        try:
            if source_is_audio:
                active_speech_token: str | None = None
                if use_google_speech and speech_access_token is None:
                    speech_access_token = get_google_access_token(scopes=[CLOUD_PLATFORM_SCOPE])
                if use_google_speech:
                    active_speech_token = speech_access_token

                audio_bytes = download_file_bytes(drive_access_token, drive_file.file_id)
                if not audio_bytes:
                    skipped_empty += 1
                    _publish_progress()
                    continue

                transcription_result = transcribe_audio_bytes(
                    audio_bytes,
                    drive_file.name,
                    drive_file.mime_type,
                    access_token=active_speech_token,
                )
                normalized_content = _normalize_transcript_text(transcription_result.text)
                transcription_language = transcription_result.language
                duration_seconds = transcription_result.duration_seconds
                transcription_provider = transcription_result.provider
                transcription_confidence = transcription_result.confidence
                transcription_rescue_used = bool(transcription_result.rescue_used)
                transcription_rescue_provider = transcription_result.rescue_provider
                transcription_rescue_reason = transcription_result.rescue_reason
            else:
                content = download_text_file(drive_access_token, drive_file.file_id)
                normalized_content = _normalize_transcript_text(content)
        except UnsupportedLanguageError:
            skipped_unsupported_language += 1
            _publish_progress()
            continue
        except TranscriptionConfigurationError:
            # Fail fast on runtime configuration issues (e.g., missing API keys).
            raise
        except SpeechApiDisabledError:
            # Fail fast: this is a project-level configuration issue and retrying every file is wasteful.
            raise
        except Exception as exc:
            error_message = str(exc)
            if source_is_audio and _is_audio_too_large_error(error_message):
                skipped_audio_too_large += 1
                _publish_progress()
                continue

            if _is_empty_transcript_error(error_message):
                skipped_empty += 1
                _publish_progress()
                continue

            failed_transcription += 1
            logger.exception("Failed to transcribe/process file '%s'", drive_file.name)
            _publish_progress()
            continue

        if normalized_content:
            logger.info("Translating transcript for '%s' to English if needed.", drive_file.name)
            normalized_content = translate_to_english(normalized_content)

        if not normalized_content:
            skipped_empty += 1
            _publish_progress()
            continue

        if len(normalized_content) < settings.transcript_min_chars:
            skipped_too_short += 1
            _publish_progress()
            continue

        try:
            score, label, analysis_summary, kpis = analyze_sentiment(normalized_content)
            intent_category, intent_summary = classify_intent_summary(
                normalized_content,
                fallback_summary=analysis_summary,
            )
        except Exception:
            failed_analysis += 1
            logger.exception("Failed to analyze sentiment for file '%s'", drive_file.name)
            _publish_progress()
            continue

        final_summary = intent_summary
        if intent_category != "IGNORE" and final_summary == "IGNORE":
            final_summary = analysis_summary

        persisted_transcript: Transcript | None = None
        for attempt in range(2):
            try:
                current_transcript_id = existing_transcript_id
                if current_transcript_id is None:
                    current_transcript_id = db.scalar(
                        select(Transcript.id).where(Transcript.drive_file_id == drive_file.file_id)
                    )

                if current_transcript_id:
                    transcript = db.get(Transcript, current_transcript_id)
                    if transcript is None:
                        transcript = Transcript(
                            drive_file_id=drive_file.file_id,
                            file_name=drive_file.name,
                            modified_time=drive_file.modified_time,
                            content=normalized_content,
                            source_type=source_type,
                            transcription_language=transcription_language,
                            transcription_status="completed",
                            duration_seconds=duration_seconds,
                            transcription_provider=transcription_provider,
                            transcription_confidence=transcription_confidence,
                            transcription_rescue_used=transcription_rescue_used,
                            transcription_rescue_provider=transcription_rescue_provider,
                            transcription_rescue_reason=transcription_rescue_reason,
                        )
                        db.add(transcript)
                        db.flush()
                        is_reprocess_target = False
                    else:
                        transcript.file_name = drive_file.name
                        transcript.modified_time = drive_file.modified_time
                        transcript.content = normalized_content
                        transcript.source_type = source_type
                        transcript.transcription_language = transcription_language
                        transcript.transcription_status = "completed"
                        transcript.duration_seconds = duration_seconds
                        transcript.transcription_provider = transcription_provider
                        transcript.transcription_confidence = transcription_confidence
                        transcript.transcription_rescue_used = transcription_rescue_used
                        transcript.transcription_rescue_provider = transcription_rescue_provider
                        transcript.transcription_rescue_reason = transcription_rescue_reason
                else:
                    transcript = Transcript(
                        drive_file_id=drive_file.file_id,
                        file_name=drive_file.name,
                        modified_time=drive_file.modified_time,
                        content=normalized_content,
                        source_type=source_type,
                        transcription_language=transcription_language,
                        transcription_status="completed",
                        duration_seconds=duration_seconds,
                        transcription_provider=transcription_provider,
                        transcription_confidence=transcription_confidence,
                        transcription_rescue_used=transcription_rescue_used,
                        transcription_rescue_provider=transcription_rescue_provider,
                        transcription_rescue_reason=transcription_rescue_reason,
                    )
                    db.add(transcript)
                    db.flush()

                kpis["call_id"] = str(transcript.id)
                kpis["intent_category"] = intent_category
                kpis["intent_summary"] = final_summary
                kpis["source_type"] = source_type
                if transcription_language:
                    kpis["transcription_language"] = transcription_language
                if transcription_provider:
                    kpis["transcription_provider"] = transcription_provider
                if transcription_confidence is not None:
                    kpis["transcription_confidence"] = round(float(transcription_confidence), 4)
                if transcription_rescue_used:
                    kpis["transcription_rescue_used"] = True
                if transcription_rescue_provider:
                    kpis["transcription_rescue_provider"] = transcription_rescue_provider
                if transcription_rescue_reason:
                    kpis["transcription_rescue_reason"] = transcription_rescue_reason

                concerns = kpis.get("parent_concerns") or []
                if not isinstance(concerns, list):
                    concerns = []

                keywords = ", ".join(str(item).strip() for item in concerns if str(item).strip())
                sentiment = db.scalar(select(Sentiment).where(Sentiment.transcript_id == transcript.id))
                if sentiment:
                    sentiment.score = score
                    sentiment.label = label
                    sentiment.intent_category = intent_category
                    sentiment.summary = final_summary
                    sentiment.kpi_json = json.dumps(kpis, ensure_ascii=False)
                    sentiment.explanation = analysis_summary
                    sentiment.keywords = keywords
                else:
                    sentiment = Sentiment(
                        transcript_id=transcript.id,
                        score=score,
                        label=label,
                        intent_category=intent_category,
                        summary=final_summary,
                        kpi_json=json.dumps(kpis, ensure_ascii=False),
                        explanation=analysis_summary,
                        keywords=keywords,
                    )
                    db.add(sentiment)

                # Persist each file immediately to avoid losing the full batch
                # on transient DB disconnects.
                db.commit()
                persisted_transcript = transcript
                break
            except Exception as exc:
                db.rollback()
                if attempt == 0 and _is_db_connection_closed_error(str(exc)):
                    logger.warning(
                        "Transient DB disconnect while persisting '%s'; retrying once.",
                        drive_file.name,
                    )
                    continue
                raise

        if persisted_transcript is None:
            continue

        created += 1
        if is_reprocess_target:
            reprocessed += 1

        if len(processed_records) < MAX_RESULT_TRANSCRIPTS:
            processed_records.append(
                {
                    "transcript_id": int(persisted_transcript.id),
                    "file_name": persisted_transcript.file_name,
                    "created_at": persisted_transcript.created_at,
                    "source_type": source_type,
                    "transcription_language": transcription_language,
                    "transcription_provider": transcription_provider,
                    "transcription_confidence": transcription_confidence,
                    "transcription_rescue_used": transcription_rescue_used,
                    "transcription_rescue_provider": transcription_rescue_provider,
                    "transcription_rescue_reason": transcription_rescue_reason,
                    "label": label,
                    "intent_category": intent_category,
                    "summary": final_summary,
                    "content": _truncate_preview(normalized_content),
                }
            )

        _publish_progress()

    # Ensure no pending transaction remains before returning status payload.
    if db.in_transaction():
        db.commit()

    skipped_total = (
        skipped_duplicate
        + skipped_non_transcript
        + skipped_too_short
        + skipped_unsupported_language
        + skipped_audio_too_large
        + skipped_audio_unsupported
        + skipped_empty
        + skipped_reprocess_filter
    )

    return {
        "processed": created,
        "reprocessed": reprocessed,
        "skipped": skipped_total,
        "skipped_total": skipped_total,
        "skipped_duplicate": skipped_duplicate,
        "skipped_non_transcript": skipped_non_transcript,
        "skipped_too_short": skipped_too_short,
        "skipped_unsupported_language": skipped_unsupported_language,
        "skipped_audio_too_large": skipped_audio_too_large,
        "skipped_audio_unsupported": skipped_audio_unsupported,
        "skipped_empty": skipped_empty,
        "skipped_reprocess_filter": skipped_reprocess_filter,
        "failed_transcription": failed_transcription,
        "failed_analysis": failed_analysis,
        "total_seen": len(drive_files),
        "audio_seen": len(audio_files),
        "text_seen": len(txt_files),
        "examined": examined,
        "attempted": attempted,
        "folder_id": resolved_folder_id,
        "force_reprocess": force_reprocess,
        "reprocess_ignore_only": reprocess_ignore_only,
        "audio_only": audio_only,
        "processed_records": processed_records,
    }
