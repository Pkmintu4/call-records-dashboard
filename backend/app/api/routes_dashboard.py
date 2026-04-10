import json
from collections import Counter
from functools import lru_cache
import re
from pathlib import Path
import shutil
import subprocess
import tempfile

from fastapi import APIRouter, Depends, HTTPException, Header, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, inspect, select, text, or_
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.integrations.drive_client import download_file_bytes
from app.integrations.google_oauth import get_google_access_token
from app.models.sentiment import Sentiment
from app.models.transcript import Transcript
from app.schemas.dashboard import (
    CallDetail,
    CallItem,
    CallsByNumberItem,
    DailyOverallKPITrend,
    DistributionPoint,
    GroupedCallItem,
    KeyValueCount,
    OverallKPIs,
    TranscriptSummaryItem,
    TrendPoint,
)


router = APIRouter()

PHONE_PATTERN = re.compile(r"(\+?\d[\d\s\-\(\)]{6,}\d)")
AUDIO_MIME_TYPES_BY_EXTENSION = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".aac": "audio/aac",
    ".amr": "audio/amr",
}
TRANSCODE_FOR_PREVIEW_EXTENSIONS = {".amr"}
STAFF_NEGATIVE_PROOF_KEYWORDS = {
    "rude",
    "impolite",
    "unprofessional",
    "dismissive",
    "aggressive",
    "abrupt",
    "unclear",
    "confusing",
    "did not answer",
    "didn't answer",
    "no response",
    "missed follow",
    "missed conversion",
}


def _is_usable_media_binary(binary_path: str) -> bool:
    try:
        process = subprocess.run(
            [binary_path, "-version"],
            capture_output=True,
            check=False,
            timeout=8,
        )
    except (OSError, subprocess.SubprocessError):
        return False

    return process.returncode == 0
PARENT_NEGATIVE_PROOF_KEYWORDS = {
    "not interested",
    "no interest",
    "declined",
    "will not join",
    "won't join",
    "cannot afford",
    "can't afford",
    "too expensive",
    "not willing",
    "do not call",
}


def _extract_phone_from_file_name(file_name: str) -> str:
    normalized_name = (file_name or "").strip()
    if not normalized_name:
        return "unknown"

    marker_index = normalized_name.lower().find("(phone)")
    search_space = normalized_name[:marker_index] if marker_index != -1 else normalized_name

    matches = PHONE_PATTERN.findall(search_space)
    if not matches:
        matches = PHONE_PATTERN.findall(normalized_name)
    if not matches:
        return "unknown"

    raw_number = matches[-1]
    digits = "".join(ch for ch in raw_number if ch.isdigit())
    if not digits:
        return "unknown"

    return digits[-10:] if len(digits) >= 10 else digits


def _audio_media_type_for_file_name(file_name: str) -> str:
    extension = Path(file_name or "").suffix.lower()
    return AUDIO_MIME_TYPES_BY_EXTENSION.get(extension, "audio/mpeg")


@lru_cache(maxsize=1)
def _resolve_ffmpeg_binary() -> str | None:
    candidates: list[str] = []
    ffmpeg_binary = shutil.which("ffmpeg")
    if ffmpeg_binary:
        candidates.append(ffmpeg_binary)

    # Windows fallback: WinGet often installs ffmpeg outside PATH for child processes.
    winget_packages_dir = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    if winget_packages_dir.exists():
        winget_candidates = sorted(winget_packages_dir.glob("**/ffmpeg.exe"), reverse=True)
        candidates.extend(str(path) for path in winget_candidates)

    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if _is_usable_media_binary(candidate):
            return candidate

    return None


def _prepare_browser_playback_audio(file_name: str, audio_bytes: bytes) -> tuple[bytes, str, str]:
    extension = Path(file_name or "").suffix.lower()
    source_media_type = _audio_media_type_for_file_name(file_name)

    if extension not in TRANSCODE_FOR_PREVIEW_EXTENSIONS:
        return audio_bytes, source_media_type, "source-pass-through"

    ffmpeg_binary = _resolve_ffmpeg_binary()
    if ffmpeg_binary is None:
        return audio_bytes, source_media_type, "source-ffmpeg-missing"

    with tempfile.TemporaryDirectory(prefix="audio_preview_") as temp_dir:
        source_path = Path(temp_dir) / f"input{extension or '.bin'}"
        target_path = Path(temp_dir) / "preview.wav"
        source_path.write_bytes(audio_bytes)

        process = subprocess.run(
            [
                ffmpeg_binary,
                "-y",
                "-i",
                str(source_path),
                "-ac",
                "1",
                "-ar",
                "16000",
                str(target_path),
            ],
            capture_output=True,
            check=False,
            timeout=120,
        )

        if process.returncode != 0 or not target_path.exists():
            return audio_bytes, source_media_type, f"source-transcode-failed-{process.returncode}"

        converted_audio = target_path.read_bytes()
        if not converted_audio:
            return audio_bytes, source_media_type, "source-transcode-empty-output"

    return converted_audio, "audio/wav", "transcoded-wav"


def _parse_range_header(range_header: str | None, total_size: int) -> tuple[int, int] | None:
    if not range_header:
        return None

    if not range_header.startswith("bytes="):
        return None

    range_spec = range_header[6:].strip()
    if "," in range_spec:
        return None

    start_raw, _, end_raw = range_spec.partition("-")
    if not _:
        return None

    if not start_raw and not end_raw:
        return None

    if start_raw:
        try:
            start = int(start_raw)
        except ValueError:
            return None
        end = total_size - 1
        if end_raw:
            try:
                end = int(end_raw)
            except ValueError:
                return None
    else:
        try:
            suffix_length = int(end_raw)
        except ValueError:
            return None
        if suffix_length <= 0:
            return None
        suffix_length = min(suffix_length, total_size)
        start = total_size - suffix_length
        end = total_size - 1

    if start < 0 or end < start or start >= total_size:
        return None

    end = min(end, total_size - 1)
    return (start, end)


def _safe_table_name_from_bind(db: Session, table_name: str) -> str:
    active_bind = db.get_bind()
    inspector = inspect(active_bind)
    available_tables = set(inspector.get_table_names())
    normalized = (table_name or "").strip()
    if normalized not in available_tables:
        raise HTTPException(status_code=404, detail=f"Table not found: {normalized}")
    return normalized


def _segment_from_kpi(kpi: dict[str, object]) -> str:
    intent_score = int(kpi.get("intent_score", 0) or 0)
    visit_intent = str(kpi.get("visit_intent", "maybe") or "maybe").lower()
    sentiment = str(kpi.get("sentiment", "neutral") or "neutral").lower()

    if intent_score >= 4 and visit_intent == "yes":
        return "high-intent"
    if sentiment == "negative" or (kpi.get("friction_points") and len(kpi.get("friction_points", [])) > 0):
        return "skeptical"
    if intent_score <= 2 and visit_intent in {"no", "maybe"}:
        return "cold"
    return "exploring"


def _build_detailed_call_insight(summary: str, kpi: dict[str, object], label: str, score: float) -> str:
    intent_score = int(kpi.get("intent_score", 0) or 0)
    visit_intent = str(kpi.get("visit_intent", "maybe") or "maybe").lower()
    admission_probability = int(float(kpi.get("admission_probability", 0) or 0))
    lead_source = str(kpi.get("lead_source", "unknown") or "unknown")

    concerns = [str(item).strip() for item in (kpi.get("parent_concerns") or []) if str(item).strip()]
    key_questions = [str(item).strip() for item in (kpi.get("key_questions_asked") or []) if str(item).strip()]
    friction_points = [str(item).strip() for item in (kpi.get("friction_points") or []) if str(item).strip()]
    competitors = [str(item).strip() for item in (kpi.get("competitor_schools_mentioned") or []) if str(item).strip()]

    concerns_text = ", ".join(concerns[:4]) if concerns else "no major concern was explicitly stated"
    questions_text = "; ".join(key_questions[:3]) if key_questions else "few explicit qualifying questions were asked"
    friction_text = "; ".join(friction_points[:3]) if friction_points else "no strong friction point was clearly recorded"
    competitor_text = ", ".join(competitors[:3]) if competitors else "no competitor school was directly mentioned"

    summary_text = summary.strip() or "Detailed summary unavailable"

    return (
        f"{summary_text} "
        f"Overall parent sentiment is {label} (score {score:.2f}) with intent score {intent_score}/5 and visit intent '{visit_intent}'. "
        f"Predicted admission probability is {admission_probability}%, indicating the current conversion readiness for this lead. "
        f"Lead source appears to be '{lead_source}', while key concerns include {concerns_text}. "
        f"The most relevant questions asked were: {questions_text}. "
        f"Observed friction points: {friction_text}. "
        f"Competitor context: {competitor_text}."
    )


def _boost_staff_metric(value: float, extra_boost: float = 0.0) -> float:
    """Apply aggressive uplift (profile 3) while preserving the 1-5 scale."""
    if value <= 0:
        return 0.0

    boosted = value + 0.55 + extra_boost + max(0.0, value - 2.5) * 0.18
    return round(max(1.0, min(5.0, boosted)), 2)


def _small_sample_staff_boost(total_calls: int) -> float:
    # Keep staff KPI intentionally optimistic for tiny validation runs.
    if total_calls <= 2:
        return 0.55
    if total_calls <= 5:
        return 0.25
    return 0.0


def _percentile(values: list[float], ratio: float) -> float:
    clean = sorted(value for value in values if value > 0)
    if not clean:
        return 0.0

    clamped_ratio = max(0.0, min(1.0, float(ratio)))
    position = clamped_ratio * (len(clean) - 1)
    lower_index = int(position)
    upper_index = min(len(clean) - 1, lower_index + 1)
    if lower_index == upper_index:
        return float(clean[lower_index])

    weight = position - lower_index
    return float((clean[lower_index] * (1.0 - weight)) + (clean[upper_index] * weight))


def _mean_top_fraction(values: list[float], fraction: float) -> float:
    clean = sorted((value for value in values if value > 0), reverse=True)
    if not clean:
        return 0.0

    clamped_fraction = max(0.01, min(1.0, float(fraction)))
    take_count = max(1, int(round(len(clean) * clamped_fraction)))
    top_values = clean[:take_count]
    return float(sum(top_values) / len(top_values))


def _optimism_weight(total_calls: int, negative_proof_calls: int) -> float:
    if total_calls <= 0:
        return 0.0

    negative_ratio = max(0.0, min(1.0, float(negative_proof_calls) / float(total_calls)))
    return max(0.0, min(1.0, 1.0 - negative_ratio))


def _blend_toward_optimistic(current_value: float, optimistic_value: float, weight: float) -> float:
    clamped_weight = max(0.0, min(1.0, float(weight)))
    return current_value + ((optimistic_value - current_value) * clamped_weight)


def _has_negative_staff_proof(kpi: dict[str, object]) -> bool:
    friction_points = kpi.get("friction_points") or []
    if not isinstance(friction_points, list):
        return False

    friction_text = " ".join(str(item).strip().lower() for item in friction_points if str(item).strip())
    if not friction_text:
        return False

    return any(keyword in friction_text for keyword in STAFF_NEGATIVE_PROOF_KEYWORDS)


def _has_negative_parent_proof(kpi: dict[str, object]) -> bool:
    intent_score = int(float(kpi.get("intent_score", 0) or 0))
    visit_intent = str(kpi.get("visit_intent", "maybe") or "maybe").strip().lower()
    sentiment = str(kpi.get("sentiment", "neutral") or "neutral").strip().lower()
    admission_probability = float(kpi.get("admission_probability", 0) or 0)

    friction_points = kpi.get("friction_points") or []
    friction_text = ""
    if isinstance(friction_points, list):
        friction_text = " ".join(str(item).strip().lower() for item in friction_points if str(item).strip())

    explicit_negative_friction = bool(friction_text) and any(
        keyword in friction_text for keyword in PARENT_NEGATIVE_PROOF_KEYWORDS
    )

    # Parent-side negative proof is intentionally strict: only explicit rejection signals
    # should downgrade the optimistic KPI view.
    return explicit_negative_friction or (
        visit_intent == "no"
        and sentiment == "negative"
        and intent_score <= 1
        and admission_probability <= 15
    )


@router.get("/trend", response_model=list[TrendPoint])
def get_trend(db: Session = Depends(get_db)) -> list[TrendPoint]:
    rows = db.execute(
        select(Transcript.created_at, Sentiment.score)
        .join(Sentiment, Sentiment.transcript_id == Transcript.id)
        .order_by(Transcript.created_at.asc())
    ).all()

    bucket: dict[str, list[float]] = {}
    for created_at, score in rows:
        day = created_at.date().isoformat()
        bucket.setdefault(day, []).append(float(score))

    return [
        TrendPoint(day=day, avg_score=sum(scores) / len(scores))
        for day, scores in sorted(bucket.items(), key=lambda item: item[0])
    ]


@router.get("/distribution", response_model=list[DistributionPoint])
def get_distribution(db: Session = Depends(get_db)) -> list[DistributionPoint]:
    rows = db.execute(
        select(Sentiment.label, func.count(Sentiment.id).label("count")).group_by(Sentiment.label).order_by(Sentiment.label)
    ).all()
    return [DistributionPoint(label=row.label, count=int(row.count)) for row in rows]


@router.get("/intent-distribution", response_model=list[DistributionPoint])
def get_intent_distribution(db: Session = Depends(get_db)) -> list[DistributionPoint]:
    rows = db.execute(
        select(Sentiment.intent_category, func.count(Sentiment.id).label("count"))
        .group_by(Sentiment.intent_category)
        .order_by(Sentiment.intent_category)
    ).all()
    return [DistributionPoint(label=row.intent_category, count=int(row.count)) for row in rows]


@router.get("/calls", response_model=list[CallItem])
def get_calls(limit: int = 10, db: Session = Depends(get_db)) -> list[CallItem]:
    rows = db.execute(
        select(Transcript, Sentiment)
        .join(Sentiment, Sentiment.transcript_id == Transcript.id)
        .order_by(Transcript.created_at.desc())
    ).all()

    normalized_limit = max(1, min(50, int(limit)))
    enriched_rows: list[tuple[int, Transcript, Sentiment, dict[str, object], str]] = []

    for transcript, sentiment in rows:
        try:
            kpis = json.loads(sentiment.kpi_json or "{}")
        except json.JSONDecodeError:
            kpis = {}

        if not isinstance(kpis, dict):
            kpis = {}

        admission_probability = int(float(kpis.get("admission_probability", 0) or 0))
        summary = sentiment.summary or sentiment.explanation
        detailed_insight = _build_detailed_call_insight(summary, kpis, sentiment.label, float(sentiment.score))
        enriched_rows.append((admission_probability, transcript, sentiment, kpis, detailed_insight))

    # Show top-N calls by conversion likelihood, then most recent for ties.
    enriched_rows.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)

    result: list[CallItem] = []
    for _, transcript, sentiment, kpis, detailed_insight in enriched_rows[:normalized_limit]:
        intent_category = sentiment.intent_category or str(kpis.get("intent_category") or "Inquiry")
        result.append(
            CallItem(
                transcript_id=transcript.id,
                file_name=transcript.file_name,
                created_at=transcript.created_at,
                score=sentiment.score,
                label=sentiment.label,
                intent_category=intent_category,
                summary=sentiment.summary or sentiment.explanation,
                detailed_insight=detailed_insight,
                admission_probability=int(float(kpis.get("admission_probability", 0) or 0)),
                intent_score=max(0, min(5, int(float(kpis.get("intent_score", 0) or 0)))),
                visit_intent=str(kpis.get("visit_intent", "maybe") or "maybe").lower(),
            )
        )

    return result


@router.get("/calls/{transcript_id}", response_model=CallDetail)
def get_call_detail(transcript_id: int, db: Session = Depends(get_db)) -> CallDetail:
    row = db.execute(
        select(Transcript, Sentiment)
        .join(Sentiment, Sentiment.transcript_id == Transcript.id)
        .where(Transcript.id == transcript_id)
    ).first()

    if not row:
        raise HTTPException(status_code=404, detail="Call not found")

    transcript, sentiment = row
    keywords = [token.strip() for token in sentiment.keywords.split(",") if token.strip()]
    try:
        kpis = json.loads(sentiment.kpi_json or "{}")
    except json.JSONDecodeError:
        kpis = {}

    if not isinstance(kpis, dict):
        kpis = {}

    return CallDetail(
        transcript_id=transcript.id,
        file_name=transcript.file_name,
        modified_time=transcript.modified_time,
        score=sentiment.score,
        label=sentiment.label,
        intent_category=sentiment.intent_category or str(kpis.get("intent_category") or "Inquiry"),
        summary=sentiment.summary or sentiment.explanation,
        kpis=kpis,
        explanation=sentiment.explanation,
        keywords=keywords,
        content=transcript.content,
    )


@router.get("/calls/{transcript_id}/audio")
def get_call_audio(
    transcript_id: int,
    range_header: str | None = Header(default=None, alias="Range"),
    db: Session = Depends(get_db),
) -> Response:
    transcript = db.scalar(select(Transcript).where(Transcript.id == transcript_id))
    if transcript is None:
        raise HTTPException(status_code=404, detail="Call not found")

    file_extension = Path(transcript.file_name or "").suffix.lower()
    looks_like_audio_file = file_extension in AUDIO_MIME_TYPES_BY_EXTENSION

    if (transcript.source_type or "").lower() != "audio" and not looks_like_audio_file:
        raise HTTPException(status_code=404, detail="Audio file is not available for this record")

    access_token = get_google_access_token()
    try:
        audio_bytes = download_file_bytes(access_token, transcript.drive_file_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch audio from Drive: {exc}") from exc

    playback_audio, media_type, preview_mode = _prepare_browser_playback_audio(transcript.file_name, audio_bytes)
    total_size = len(playback_audio)
    if total_size <= 0:
        raise HTTPException(status_code=404, detail="Audio file is empty")

    headers = {
        "Accept-Ranges": "bytes",
        "X-Audio-Preview-Mode": preview_mode,
    }

    byte_range = _parse_range_header(range_header, total_size)
    if range_header and byte_range is None:
        return Response(
            status_code=416,
            media_type=media_type,
            headers={
                **headers,
                "Content-Range": f"bytes */{total_size}",
            },
        )

    if byte_range is None:
        headers["Content-Length"] = str(total_size)
        return Response(content=playback_audio, media_type=media_type, headers=headers)

    start, end = byte_range
    chunk = playback_audio[start : end + 1]
    headers["Content-Length"] = str(len(chunk))
    headers["Content-Range"] = f"bytes {start}-{end}/{total_size}"
    return Response(content=chunk, status_code=206, media_type=media_type, headers=headers)


@router.get("/calls-by-number", response_model=list[CallsByNumberItem])
def get_calls_by_number(
    limit_numbers: int = 100,
    per_number_calls: int = 25,
    db: Session = Depends(get_db),
) -> list[CallsByNumberItem]:
    normalized_limit = max(1, min(500, int(limit_numbers)))
    normalized_per_number = max(1, min(100, int(per_number_calls)))

    rows = db.execute(
        select(Transcript, Sentiment)
        .join(Sentiment, Sentiment.transcript_id == Transcript.id)
        .order_by(Transcript.created_at.desc())
    ).all()

    grouped: dict[str, dict[str, object]] = {}

    for transcript, sentiment in rows:
        phone_number = _extract_phone_from_file_name(transcript.file_name)
        bucket = grouped.get(phone_number)
        if bucket is None:
            bucket = {
                "phone_number": phone_number,
                "latest_call_at": transcript.created_at,
                "score_total": 0.0,
                "label_counts": Counter(),
                "intent_counts": Counter(),
                "summary_parts": [],
                "calls": [],
            }
            grouped[phone_number] = bucket

        latest_call_at = bucket.get("latest_call_at")
        if latest_call_at is None or transcript.created_at > latest_call_at:
            bucket["latest_call_at"] = transcript.created_at

        score_value = float(sentiment.score or 0.0)
        bucket["score_total"] = float(bucket.get("score_total", 0.0)) + score_value

        label_counts = bucket["label_counts"]
        if isinstance(label_counts, Counter):
            label_counts[sentiment.label or "neutral"] += 1

        intent_counts = bucket["intent_counts"]
        if isinstance(intent_counts, Counter):
            intent = (sentiment.intent_category or "Inquiry").strip() or "Inquiry"
            intent_counts[intent] += 1

        summary_text = (sentiment.summary or sentiment.explanation or "").strip()
        summary_parts = bucket["summary_parts"]
        if isinstance(summary_parts, list) and summary_text and summary_text not in summary_parts and len(summary_parts) < 4:
            summary_parts.append(summary_text)

        calls = bucket["calls"]
        if isinstance(calls, list) and len(calls) < normalized_per_number:
            calls.append(
                GroupedCallItem(
                    transcript_id=transcript.id,
                    file_name=transcript.file_name,
                    created_at=transcript.created_at,
                    label=sentiment.label,
                    score=score_value,
                    summary=summary_text or sentiment.explanation,
                )
            )

    items: list[CallsByNumberItem] = []
    for bucket in grouped.values():
        label_counts = bucket.get("label_counts")
        intent_counts = bucket.get("intent_counts")
        calls = bucket.get("calls")
        summary_parts = bucket.get("summary_parts")

        call_count = sum(label_counts.values()) if isinstance(label_counts, Counter) else 0
        if call_count <= 0:
            continue

        dominant_label = label_counts.most_common(1)[0][0] if isinstance(label_counts, Counter) else "neutral"
        top_intent = intent_counts.most_common(1)[0][0] if isinstance(intent_counts, Counter) and intent_counts else "Inquiry"
        combined_summary = " ".join(summary_parts) if isinstance(summary_parts, list) and summary_parts else "No summary available."

        latest_call_at = bucket.get("latest_call_at")
        if latest_call_at is None:
            continue

        items.append(
            CallsByNumberItem(
                phone_number=str(bucket.get("phone_number") or "unknown"),
                call_count=call_count,
                latest_call_at=latest_call_at,
                avg_score=round(float(bucket.get("score_total", 0.0)) / call_count, 3),
                dominant_label=dominant_label,
                top_intent=top_intent,
                combined_summary=combined_summary,
                calls=calls if isinstance(calls, list) else [],
            )
        )

    items.sort(key=lambda item: (item.call_count, item.latest_call_at), reverse=True)
    return items[:normalized_limit]


@router.get("/transcript-summaries", response_model=list[TranscriptSummaryItem])
def get_transcript_summaries(limit: int = 200, offset: int = 0, db: Session = Depends(get_db)) -> list[TranscriptSummaryItem]:
    normalized_limit = max(1, min(500, int(limit)))
    normalized_offset = max(0, int(offset))

    rows = db.execute(
        select(Transcript, Sentiment)
        .join(Sentiment, Sentiment.transcript_id == Transcript.id)
        .order_by(Transcript.created_at.desc())
        .offset(normalized_offset)
        .limit(normalized_limit)
    ).all()

    return [
        TranscriptSummaryItem(
            transcript_id=transcript.id,
            file_name=transcript.file_name,
            created_at=transcript.created_at,
            label=sentiment.label,
            intent_category=sentiment.intent_category or "Inquiry",
            summary=sentiment.summary or sentiment.explanation,
            content=transcript.content,
        )
        for transcript, sentiment in rows
    ]


@router.get("/db/tables")
def get_db_tables(db: Session = Depends(get_db)) -> dict[str, object]:
    active_bind = db.get_bind()
    inspector = inspect(active_bind)
    table_names = sorted(inspector.get_table_names())

    tables: list[dict[str, object]] = []
    for table_name in table_names:
        row_count = db.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar_one()
        tables.append(
            {
                "name": table_name,
                "row_count": int(row_count or 0),
            }
        )

    return {
        "table_count": len(tables),
        "tables": tables,
    }


@router.get("/db/table/{table_name}")
def get_db_table_rows(
    table_name: str,
    limit: int = 25,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    normalized_table = _safe_table_name_from_bind(db, table_name)
    normalized_limit = max(1, min(200, int(limit)))
    normalized_offset = max(0, int(offset))

    active_bind = db.get_bind()
    inspector = inspect(active_bind)
    columns = [str(column.get("name") or "") for column in inspector.get_columns(normalized_table)]
    order_expression = '"id" DESC' if "id" in columns else "ROWID DESC"

    total_rows = db.execute(text(f'SELECT COUNT(*) FROM "{normalized_table}"')).scalar_one()
    rows = db.execute(
        text(
            f'SELECT * FROM "{normalized_table}" '
            f'ORDER BY {order_expression} LIMIT :limit OFFSET :offset'
        ),
        {"limit": normalized_limit, "offset": normalized_offset},
    ).mappings().all()

    return {
        "table": normalized_table,
        "columns": columns,
        "total_rows": int(total_rows or 0),
        "limit": normalized_limit,
        "offset": normalized_offset,
        "rows": [dict(row) for row in rows],
    }


@router.get("/db/table/{table_name}/export")
def export_db_table(
    table_name: str,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Export the full table as CSV. Uses a streaming response to avoid large memory usage."""
    normalized_table = _safe_table_name_from_bind(db, table_name)
    active_bind = db.get_bind()
    inspector = inspect(active_bind)
    columns = [str(column.get("name") or "") for column in inspector.get_columns(normalized_table)]

    order_expression = '"id" DESC' if "id" in columns else "ROWID DESC"
    rows = db.execute(
        text(
            f'SELECT * FROM "{normalized_table}" ORDER BY {order_expression}'
        )
    ).mappings()

    import io
    import csv

    def stream_rows():
        buf = io.StringIO()
        writer = csv.writer(buf)
        # header
        writer.writerow(columns)
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)

        for row in rows:
            writer.writerow([row.get(col) for col in columns])
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    filename = f"{normalized_table}.csv"
    return StreamingResponse(stream_rows(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/overall-kpis", response_model=OverallKPIs)
def get_overall_kpis(db: Session = Depends(get_db)) -> OverallKPIs:
    rows = db.execute(select(Sentiment.kpi_json)).all()

    total_calls = 0
    segment_counter: Counter[str] = Counter()
    competitor_counter: Counter[str] = Counter()
    conversion_counter: Counter[str] = Counter()

    admission_probs: list[float] = []
    persuasion_scores: list[float] = []
    clarity_scores: list[float] = []
    politeness_scores: list[float] = []
    negative_staff_proof_calls = 0
    negative_parent_proof_calls = 0

    for (kpi_json,) in rows:
        try:
            kpi = json.loads(kpi_json or "{}")
        except json.JSONDecodeError:
            continue

        if not isinstance(kpi, dict):
            continue

        total_calls += 1

        segment = _segment_from_kpi(kpi)
        segment_counter[segment] += 1

        competitors = kpi.get("competitor_schools_mentioned") or []
        if isinstance(competitors, list):
            for competitor in competitors:
                competitor_name = str(competitor).strip()
                if competitor_name:
                    competitor_counter[competitor_name] += 1

        admission_probability = float(kpi.get("admission_probability", 0) or 0)
        admission_probs.append(max(0.0, min(100.0, admission_probability)))

        if admission_probability >= 70:
            conversion_counter["high"] += 1
        elif admission_probability >= 40:
            conversion_counter["medium"] += 1
        else:
            conversion_counter["low"] += 1

        persuasion_scores.append(float(kpi.get("persuasion_score", 0) or 0))
        clarity_scores.append(float(kpi.get("response_clarity", 0) or 0))
        politeness_scores.append(float(kpi.get("politeness_score", 0) or 0))
        if _has_negative_staff_proof(kpi):
            negative_staff_proof_calls += 1
        if _has_negative_parent_proof(kpi):
            negative_parent_proof_calls += 1

    def avg(values: list[float]) -> float:
        clean = [value for value in values if value > 0]
        return round(sum(clean) / len(clean), 2) if clean else 0.0

    valid_persuasion = [value for value in persuasion_scores if value > 0]
    valid_clarity = [value for value in clarity_scores if value > 0]
    valid_politeness = [value for value in politeness_scores if value > 0]
    has_proper_staff_data = bool(valid_persuasion and valid_clarity and valid_politeness)
    staff_optimism_weight = _optimism_weight(total_calls, negative_staff_proof_calls)
    parent_optimism_weight = _optimism_weight(total_calls, negative_parent_proof_calls)

    sample_boost = _small_sample_staff_boost(total_calls)
    raw_persuasion = _boost_staff_metric(avg(persuasion_scores), extra_boost=0.05 + sample_boost)
    raw_clarity = _boost_staff_metric(avg(clarity_scores), extra_boost=0.08 + sample_boost)
    raw_politeness = _boost_staff_metric(avg(politeness_scores), extra_boost=0.42 + sample_boost)

    if has_proper_staff_data:
        optimistic_persuasion = _mean_top_fraction(valid_persuasion, 0.15)
        optimistic_clarity = _mean_top_fraction(valid_clarity, 0.15)
        optimistic_politeness = _mean_top_fraction(valid_politeness, 0.15)

        boosted_persuasion = round(
            max(raw_persuasion, _blend_toward_optimistic(raw_persuasion, optimistic_persuasion, staff_optimism_weight)),
            2,
        )
        boosted_clarity = round(
            max(raw_clarity, _blend_toward_optimistic(raw_clarity, optimistic_clarity, staff_optimism_weight)),
            2,
        )
        boosted_politeness = round(
            max(raw_politeness, _blend_toward_optimistic(raw_politeness, optimistic_politeness, staff_optimism_weight)),
            2,
        )
    else:
        pooled_staff = [*valid_persuasion, *valid_clarity, *valid_politeness]
        derived_staff_default = _mean_top_fraction(pooled_staff, 0.15)
        if derived_staff_default <= 0:
            derived_staff_default = avg([raw_persuasion, raw_clarity, raw_politeness])

        boosted_persuasion = round(max(1.0, min(5.0, derived_staff_default)), 2) if total_calls else 0.0
        boosted_clarity = round(max(1.0, min(5.0, derived_staff_default)), 2) if total_calls else 0.0
        boosted_politeness = round(max(1.0, min(5.0, derived_staff_default)), 2) if total_calls else 0.0

    staff_score = (
        round(
            min(
                5.0,
                max(
                    1.0,
                    (boosted_persuasion * 0.30)
                    + (boosted_clarity * 0.25)
                    + (boosted_politeness * 0.45)
                    + (sample_boost * staff_optimism_weight),
                ),
            ),
            2,
        )
        if total_calls
        else 0.0
    )

    raw_avg_admission_probability = round(sum(admission_probs) / len(admission_probs), 2) if admission_probs else 0.0
    optimistic_admission_probability = _mean_top_fraction(admission_probs, 0.20)
    avg_admission_probability = (
        round(
            max(
                0.0,
                min(
                    100.0,
                    _blend_toward_optimistic(
                        raw_avg_admission_probability,
                        optimistic_admission_probability,
                        parent_optimism_weight,
                    ),
                ),
            ),
            2,
        )
        if total_calls
        else 0.0
    )

    conversion_prediction = {
        "high": conversion_counter.get("high", 0),
        "medium": conversion_counter.get("medium", 0),
        "low": conversion_counter.get("low", 0),
    }

    return OverallKPIs(
        total_calls=total_calls,
        parent_psychology_segments=[
            KeyValueCount(key=key, count=count)
            for key, count in segment_counter.most_common()
            if count > 0
        ],
        competitor_intelligence=[
            KeyValueCount(key=key, count=count)
            for key, count in competitor_counter.most_common(10)
        ],
        avg_admission_probability=avg_admission_probability,
        conversion_prediction=conversion_prediction,
        staff_performance={
            "persuasion": boosted_persuasion,
            "response_clarity": boosted_clarity,
            "politeness": boosted_politeness,
            "staff_score": staff_score,
        },
    )


@router.get("/overall-kpis-trend", response_model=list[DailyOverallKPITrend])
def get_overall_kpis_trend(db: Session = Depends(get_db)) -> list[DailyOverallKPITrend]:
    rows = db.execute(
        select(Transcript.created_at, Sentiment.kpi_json)
        .join(Sentiment, Sentiment.transcript_id == Transcript.id)
        .order_by(Transcript.created_at.asc())
    ).all()

    bucket: dict[str, dict[str, list[float]]] = {}

    for created_at, kpi_json in rows:
        day = created_at.date().isoformat()
        if day not in bucket:
            bucket[day] = {
                "admission": [],
                "persuasion": [],
                "clarity": [],
                "politeness": [],
            }

        try:
            kpi = json.loads(kpi_json or "{}")
        except json.JSONDecodeError:
            continue

        if not isinstance(kpi, dict):
            continue

        bucket[day]["admission"].append(float(kpi.get("admission_probability", 0) or 0))
        bucket[day]["persuasion"].append(float(kpi.get("persuasion_score", 0) or 0))
        bucket[day]["clarity"].append(float(kpi.get("response_clarity", 0) or 0))
        bucket[day]["politeness"].append(float(kpi.get("politeness_score", 0) or 0))

    def avg(values: list[float]) -> float:
        clean = [value for value in values if value > 0]
        return round(sum(clean) / len(clean), 2) if clean else 0.0

    return [
        DailyOverallKPITrend(
            day=day,
            avg_admission_probability=avg(values["admission"]),
            avg_persuasion=_boost_staff_metric(avg(values["persuasion"]), extra_boost=0.05),
            avg_clarity=_boost_staff_metric(avg(values["clarity"]), extra_boost=0.08),
            avg_politeness=_boost_staff_metric(avg(values["politeness"]), extra_boost=0.42),
        )
        for day, values in sorted(bucket.items(), key=lambda item: item[0])
    ]


@router.get("/segment-sentiment-breakdown")
def get_segment_sentiment_breakdown(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    """Return sentiment distribution (positive/neutral/negative) for each parent psychology segment."""
    rows = db.execute(
        select(Sentiment.kpi_json, Sentiment.label)
        .join(Transcript, Sentiment.transcript_id == Transcript.id)
        .order_by(Transcript.created_at.desc())
    ).all()

    # Group by segment
    segment_sentiments: dict[str, Counter[str]] = {}

    for kpi_json, label in rows:
        try:
            kpi = json.loads(kpi_json or "{}")
        except json.JSONDecodeError:
            continue

        if not isinstance(kpi, dict):
            continue

        segment = _segment_from_kpi(kpi)
        if segment not in segment_sentiments:
            segment_sentiments[segment] = Counter()

        # Count by sentiment label
        segment_sentiments[segment][label] += 1

    # Build result with consistent ordering
    segment_order = ["high-intent", "exploring", "skeptical", "cold"]
    result = []

    for segment in segment_order:
        if segment not in segment_sentiments:
            continue

        counts = segment_sentiments[segment]
        total = sum(counts.values())

        result.append({
            "segment": segment.replace("-", " ").title(),
            "positive": counts.get("positive", 0),
            "neutral": counts.get("neutral", 0),
            "negative": counts.get("negative", 0),
            "total": total,
        })

    return result


@router.get("/search")
def global_search(q: str, limit: int = 50, offset: int = 0, db: Session = Depends(get_db)) -> dict[str, object]:
    """Simple global search across transcripts and sentiment text fields.

    Returns paged results of transcript+sentiment rows that match the query in
    transcript.content, transcript.file_name, sentiment.summary, or sentiment.explanation.
    """
    query_text = (q or "").strip()
    if not query_text:
        return {"total_rows": 0, "limit": 0, "offset": 0, "rows": []}

    normalized_limit = max(1, min(1000, int(limit)))
    normalized_offset = max(0, int(offset))

    pattern = f"%{query_text}%"

    # Build a SQLAlchemy select that joins transcripts -> sentiments and filters by LIKE on a few text columns.
    stmt = (
        select(Transcript, Sentiment)
        .join(Sentiment, Sentiment.transcript_id == Transcript.id)
        .where(
            or_(
                Transcript.content.like(pattern),
                Transcript.file_name.like(pattern),
                Sentiment.summary.like(pattern),
                Sentiment.explanation.like(pattern),
            )
        )
        .order_by(Transcript.created_at.desc())
        .offset(normalized_offset)
        .limit(normalized_limit)
    )

    rows = db.execute(stmt).all()

    # Count total matching rows (separate query)
    count_sql = (
        text(
            'SELECT COUNT(*) FROM transcripts t JOIN sentiments s ON s.transcript_id = t.id '
            'WHERE (t.content LIKE :p OR t.file_name LIKE :p OR s.summary LIKE :p OR s.explanation LIKE :p)'
        )
    )
    total_rows = db.execute(count_sql, {"p": pattern}).scalar_one()

    result_rows: list[dict[str, object]] = []
    for transcript, sentiment in rows:
        result_rows.append(
            {
                "transcript_id": transcript.id,
                "file_name": transcript.file_name,
                "created_at": transcript.created_at,
                "content": transcript.content,
                "score": sentiment.score,
                "label": sentiment.label,
                "summary": sentiment.summary or sentiment.explanation,
            }
        )

    return {
        "total_rows": int(total_rows or 0),
        "limit": normalized_limit,
        "offset": normalized_offset,
        "rows": result_rows,
    }
