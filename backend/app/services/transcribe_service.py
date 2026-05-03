import base64
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import logging

import httpx

from app.core.config import settings
from app.integrations.google_oauth import CLOUD_PLATFORM_SCOPE, get_google_access_token


SPEECH_RECOGNIZE_URL = "https://speech.googleapis.com/v1/speech:recognize"
SPEECH_LONG_RUNNING_URL = "https://speech.googleapis.com/v1/speech:longrunningrecognize"
GOOGLE_OPERATION_BASE_URL = "https://speech.googleapis.com/v1/operations"
GEMINI_GENERATE_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".amr", ".aac"}
SUPPORTED_AUDIO_MIME_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/flac",
    "audio/x-flac",
    "audio/ogg",
    "audio/opus",
    "audio/amr",
    "audio/amr-wb",
    "audio/aac",
    "audio/mp4",
    "audio/x-m4a",
    "audio/m4a",
    "video/mp4",
}
GOOGLE_SPEECH_INLINE_MAX_BYTES = 10 * 1024 * 1024
AMR_MAGIC_NB = b"#!AMR\n"
AMR_MAGIC_WB = b"#!AMR-WB\n"
DEFAULT_LANGUAGE_CODE_BY_TAG = {
    "en": "en-IN",
    "te": "te-IN",
}
DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
TELUGU_RE = re.compile(r"[\u0C00-\u0C7F]")
logger = logging.getLogger(__name__)
NON_WORD_RE = re.compile(r"[^a-z0-9]+")
SPEAKER_TAG_RE = re.compile(r"(?i)\b(?:speaker\s*\d+|parent|caller|coordinator|agent|counselor|staff)\s*:")
ASCII_ALPHA_RE = re.compile(r"[A-Za-z]")
ASCII_TRANSCRIPT_RE = re.compile(r"[^A-Za-z0-9\s.,?!'\":;\-()/&%]")


class UnsupportedLanguageError(ValueError):
    pass


class SpeechApiDisabledError(RuntimeError):
    pass


class TranscriptionConfigurationError(RuntimeError):
    pass


@dataclass
class TranscriptionResult:
    text: str
    language: str
    duration_seconds: float | None = None
    confidence: float | None = None
    provider: str = "google_speech"
    rescue_used: bool = False
    rescue_provider: str | None = None
    rescue_reason: str | None = None


def _resolve_transcription_provider() -> str:
    provider = (settings.transcription_provider or "").strip().lower()
    return "gemini" if provider == "gemini" else "google_speech"


def uses_google_speech_provider() -> bool:
    return _resolve_transcription_provider() == "google_speech"


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


@lru_cache(maxsize=1)
def _resolve_ffmpeg_binary() -> str | None:
    candidates: list[str] = []
    ffmpeg_binary = shutil.which("ffmpeg")
    if ffmpeg_binary:
        candidates.append(ffmpeg_binary)

    # Windows fallback: WinGet may install ffmpeg outside inherited PATH.
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


@lru_cache(maxsize=1)
def _resolve_ffprobe_binary() -> str | None:
    candidates: list[str] = []
    ffprobe_binary = shutil.which("ffprobe")
    if ffprobe_binary:
        candidates.append(ffprobe_binary)

    ffmpeg_binary = _resolve_ffmpeg_binary()
    if ffmpeg_binary:
        ffprobe_candidate = Path(ffmpeg_binary).with_name("ffprobe.exe")
        if ffprobe_candidate.exists():
            candidates.append(str(ffprobe_candidate))

    winget_packages_dir = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    if winget_packages_dir.exists():
        winget_candidates = sorted(winget_packages_dir.glob("**/ffprobe.exe"), reverse=True)
        candidates.extend(str(path) for path in winget_candidates)

    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if _is_usable_media_binary(candidate):
            return candidate

    return None


def can_normalize_audio_locally() -> bool:
    return bool(settings.transcription_normalize_audio and _resolve_ffmpeg_binary() is not None)


def is_audio_transcription_supported(file_name: str, mime_type: str | None = None) -> bool:
    suffix = Path(file_name).suffix.lower()
    if suffix in SUPPORTED_AUDIO_EXTENSIONS:
        return True

    normalized_mime = (mime_type or "").strip().lower()
    if not normalized_mime:
        return False

    if normalized_mime in SUPPORTED_AUDIO_MIME_TYPES:
        return True

    # If ffmpeg is available we can normalize many additional audio/* containers/codecs.
    if normalized_mime.startswith("audio/") and can_normalize_audio_locally():
        return True

    return False


def get_transcription_max_audio_bytes() -> int:
    configured_limit = max(1, int(settings.transcription_max_audio_mb)) * 1024 * 1024
    provider = _resolve_transcription_provider()
    if provider == "google_speech":
        return min(configured_limit, GOOGLE_SPEECH_INLINE_MAX_BYTES)
    if provider == "gemini":
        gemini_limit = max(1, int(settings.gemini_transcription_inline_max_mb)) * 1024 * 1024
        return min(configured_limit, gemini_limit)
    return configured_limit


def _resolve_google_speech_language_codes() -> list[str]:
    configured = [code.strip() for code in settings.google_speech_language_codes if code.strip()]
    if not configured:
        configured = ["en-IN", "te-IN"]

    allowed_languages = {str(item).strip().lower() for item in settings.allowed_transcript_languages if str(item).strip()}
    if not allowed_languages:
        allowed_languages = {"en", "te"}

    # Primary recognition must always stay en-IN for romanized Telugu/English capture.
    if "en-IN" in configured:
        configured = ["en-IN", *[code for code in configured if code != "en-IN"]]
    else:
        configured = ["en-IN", *configured]

    filtered = [code for code in configured if _normalize_language_tag(code) in allowed_languages]
    if filtered:
        if filtered[0] != "en-IN":
            filtered = ["en-IN", *[code for code in filtered if code != "en-IN"]]
        return filtered

    fallback: list[str] = []
    for language_tag in ("en", "te"):
        if language_tag in allowed_languages:
            code = DEFAULT_LANGUAGE_CODE_BY_TAG.get(language_tag)
            if code and code not in fallback:
                fallback.append(code)

    if "en-IN" not in fallback:
        fallback = ["en-IN", *fallback]
    return fallback or ["en-IN"]


def is_audio_file(file_name: str, mime_type: str | None = None) -> bool:
    suffix = Path(file_name).suffix.lower()
    normalized_mime = (mime_type or "").lower()
    return suffix in SUPPORTED_AUDIO_EXTENSIONS or normalized_mime.startswith("audio/") or normalized_mime == "video/mp4"


def detect_language_from_text(text: str) -> str:
    normalized = " ".join(text.split())
    if not normalized:
        return "unknown"

    if TELUGU_RE.search(normalized):
        return "te"
    if DEVANAGARI_RE.search(normalized):
        return "hi"

    ascii_count = sum(1 for ch in normalized if ch.isascii())
    ascii_ratio = ascii_count / max(1, len(normalized))
    if ascii_ratio >= 0.75:
        return "en"
    return "unknown"


def _normalize_language_tag(language_tag: str) -> str:
    tag = (language_tag or "").strip().lower()
    if tag.startswith("en"):
        return "en"
    if tag.startswith("hi"):
        return "hi"
    if tag.startswith("te"):
        return "te"
    return "unknown"


def _extract_speech_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip() or f"HTTP {response.status_code}"

    error = payload.get("error")
    if isinstance(error, dict):
        message = str(error.get("message") or "").strip()
        status = str(error.get("status") or "").strip()
        if status and message:
            return f"{status}: {message}"
        if message:
            return message
    return str(payload)


def _speech_decoding_for_file(
    audio_bytes: bytes,
    file_name: str,
    mime_type: str | None = None,
) -> tuple[str | None, int | None]:
    suffix = Path(file_name).suffix.lower()

    # WAV/FLAC embed format metadata in headers. Let Google infer decoding config
    # to avoid sample-rate/bit-depth mismatches from heterogeneous recordings.
    if suffix == ".wav":
        return None, None
    if suffix == ".flac":
        return None, None

    if suffix == ".amr":
        if audio_bytes.startswith(AMR_MAGIC_WB):
            return "AMR_WB", 16000
        if audio_bytes.startswith(AMR_MAGIC_NB):
            return "AMR", 8000
        return None, None

    if suffix == ".mp3":
        return "MP3", None
    if suffix == ".ogg":
        return "OGG_OPUS", None
    if suffix == ".m4a":
        return "MP3", None
    if suffix == ".aac":
        return "MP3", None

    normalized_mime = (mime_type or "").lower()
    if normalized_mime == "audio/mpeg":
        return "MP3", None
    if "ogg" in normalized_mime:
        return "OGG_OPUS", None
    if normalized_mime == "audio/amr":
        if audio_bytes.startswith(AMR_MAGIC_WB):
            return "AMR_WB", 16000
        if audio_bytes.startswith(AMR_MAGIC_NB):
            return "AMR", 8000

    return None, None


def _mime_type_for_file(file_name: str, mime_type: str | None = None) -> str:
    suffix = Path(file_name).suffix.lower()
    if suffix == ".wav":
        return "audio/wav"
    if suffix == ".flac":
        return "audio/flac"
    if suffix == ".mp3":
        return "audio/mpeg"
    if suffix == ".ogg":
        return "audio/ogg"
    if suffix == ".amr":
        return "audio/amr"
    if suffix == ".m4a":
        return "audio/mp4"
    if suffix == ".aac":
        return "audio/aac"

    normalized_mime = (mime_type or "").strip().lower()
    if normalized_mime:
        return normalized_mime
    return "audio/flac"


def _probe_duration_seconds(file_path: Path) -> float | None:
    ffprobe_binary = _resolve_ffprobe_binary()
    if ffprobe_binary is None:
        return None

    process = subprocess.run(
        [
            ffprobe_binary,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(file_path),
        ],
        capture_output=True,
        check=False,
        timeout=20,
        text=True,
    )

    if process.returncode != 0:
        return None

    output = process.stdout.strip()
    if not output:
        return None

    try:
        duration = float(output)
    except ValueError:
        return None

    return duration if duration > 0 else None


def _build_speech_preprocess_filter() -> str | None:
    if not settings.transcription_denoise_enabled:
        return None

    # Conservative speech-first chain: remove low/high noise, suppress broadband hiss,
    # then normalize loudness to improve ASR stability across varied recordings.
    return (
        "highpass=f=120,"
        "lowpass=f=3800,"
        "afftdn=nf=-25,"
        "dynaudnorm=f=150:g=12"
    )


def _normalize_audio_with_ffmpeg(audio_bytes: bytes, file_name: str) -> tuple[bytes, str, float | None]:
    if not settings.transcription_normalize_audio:
        return audio_bytes, file_name, None

    if not can_normalize_audio_locally():
        return audio_bytes, file_name, None

    ffmpeg_binary = _resolve_ffmpeg_binary()
    if ffmpeg_binary is None:
        return audio_bytes, file_name, None

    suffix = Path(file_name).suffix.lower() or ".bin"

    with tempfile.TemporaryDirectory(prefix="normalize_audio_") as tmp_dir:
        source_path = Path(tmp_dir) / f"input{suffix}"
        target_path = Path(tmp_dir) / "normalized.flac"
        source_path.write_bytes(audio_bytes)
        source_duration = _probe_duration_seconds(source_path)

        ffmpeg_command = [
            ffmpeg_binary,
            "-y",
            "-i",
            str(source_path),
            "-ac",
            "1",
            "-ar",
            "16000",
        ]
        speech_filter = _build_speech_preprocess_filter()
        if speech_filter:
            ffmpeg_command.extend(["-af", speech_filter])
        ffmpeg_command.extend([
            "-c:a",
            "flac",
            str(target_path),
        ])

        process = subprocess.run(
            ffmpeg_command,
            capture_output=True,
            check=False,
            timeout=120,
        )
        if process.returncode != 0 or not target_path.exists():
            logger.warning("ffmpeg normalization failed for '%s'; using original audio.", file_name)
            return audio_bytes, file_name, source_duration

        converted = target_path.read_bytes()
        converted_name = f"{Path(file_name).stem}.flac"
        converted_duration = _probe_duration_seconds(target_path) or source_duration
        return converted, converted_name, converted_duration


def _split_audio_into_flac_chunks(
    audio_bytes: bytes,
    file_name: str,
    chunk_seconds: int,
) -> list[tuple[bytes, float | None]]:
    ffmpeg_binary = _resolve_ffmpeg_binary()
    if ffmpeg_binary is None:
        return []

    suffix = Path(file_name).suffix.lower() or ".bin"
    safe_chunk_seconds = max(10, int(chunk_seconds))

    with tempfile.TemporaryDirectory(prefix="split_audio_") as tmp_dir:
        source_path = Path(tmp_dir) / f"input{suffix}"
        source_path.write_bytes(audio_bytes)

        total_duration = _probe_duration_seconds(source_path)
        if total_duration is None or total_duration <= 0:
            logger.warning("Could not probe duration for '%s'; cannot chunk audio reliably.", file_name)
            return []

        configured_overlap = max(0, int(settings.transcription_chunk_overlap_seconds))
        overlap_seconds = min(configured_overlap, max(0, safe_chunk_seconds // 3), 6)
        step_seconds = max(5, safe_chunk_seconds - overlap_seconds)

        speech_filter = _build_speech_preprocess_filter()

        chunks: list[tuple[bytes, float | None]] = []
        start_seconds = 0.0
        chunk_index = 0
        while start_seconds < total_duration:
            chunk_index += 1
            segment_duration = min(float(safe_chunk_seconds), max(0.0, total_duration - start_seconds))
            if segment_duration <= 0:
                break

            chunk_path = Path(tmp_dir) / f"chunk_{chunk_index:03d}.flac"
            ffmpeg_command = [
                ffmpeg_binary,
                "-y",
                "-i",
                str(source_path),
                "-ss",
                f"{start_seconds:.3f}",
                "-t",
                f"{segment_duration:.3f}",
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
            ]
            if speech_filter:
                ffmpeg_command.extend(["-af", speech_filter])
            ffmpeg_command.extend([
                "-c:a",
                "flac",
                str(chunk_path),
            ])

            process = subprocess.run(
                ffmpeg_command,
                capture_output=True,
                check=False,
                timeout=180,
            )
            if process.returncode != 0:
                logger.warning("ffmpeg split failed for '%s' chunk %d.", file_name, chunk_index)
                break

            chunk_bytes = chunk_path.read_bytes() if chunk_path.exists() else b""
            if not chunk_bytes:
                start_seconds += step_seconds
                continue

            chunks.append((chunk_bytes, _probe_duration_seconds(chunk_path) or segment_duration))
            start_seconds += step_seconds

    return chunks


def _normalized_token_signature(token: str) -> str:
    return NON_WORD_RE.sub("", token.lower())


def _merge_chunk_transcripts(chunks: list[str]) -> str:
    merged_tokens: list[str] = []

    for chunk_text in chunks:
        raw_tokens = [token for token in chunk_text.split() if token]
        if not raw_tokens:
            continue

        if not merged_tokens:
            merged_tokens.extend(raw_tokens)
            continue

        max_overlap = min(18, len(merged_tokens), len(raw_tokens))
        overlap = 0
        for candidate in range(max_overlap, 2, -1):
            merged_window = merged_tokens[-candidate:]
            raw_window = raw_tokens[:candidate]
            merged_sig = [_normalized_token_signature(token) for token in merged_window]
            raw_sig = [_normalized_token_signature(token) for token in raw_window]
            if merged_sig == raw_sig and all(item for item in merged_sig):
                overlap = candidate
                break

        merged_tokens.extend(raw_tokens[overlap:])

    return " ".join(merged_tokens).strip()


def _build_recognition_config(
    language_codes: list[str],
    encoding: str | None,
    sample_rate_hz: int | None = None,
) -> dict[str, object]:
    config: dict[str, object] = {
        "languageCode": language_codes[0],
        "enableAutomaticPunctuation": True,
        "model": settings.google_speech_model.strip() or "phone_call",
        "useEnhanced": bool(settings.google_speech_use_enhanced),
        "metadata": {
            "interactionType": "PHONE_CALL",
            "microphoneDistance": "NEARFIELD",
            "recordingDeviceType": "SMARTPHONE",
        },
    }

    alt_language_codes = language_codes[1:4]
    if alt_language_codes:
        config["alternativeLanguageCodes"] = alt_language_codes

    if encoding:
        config["encoding"] = encoding
    if sample_rate_hz:
        config["sampleRateHertz"] = int(sample_rate_hz)

    return config


def _request_with_config_fallback(
    client: httpx.Client,
    url: str,
    body: dict[str, object],
    headers: dict[str, str],
) -> dict[str, object]:
    response = client.post(url, json=body, headers=headers)
    if response.status_code < 400:
        payload = response.json()
        if isinstance(payload, dict):
            return payload
        raise RuntimeError("Unexpected Speech-to-Text response format")

    error_message = _extract_speech_error(response)
    if response.status_code == 403 and (
        "speech-to-text api has not been used" in error_message.lower()
        or "speech.googleapis.com" in error_message.lower()
    ):
        raise SpeechApiDisabledError(
            "Google Speech-to-Text API is disabled or not yet propagated for this project. "
            "Enable speech.googleapis.com in Google Cloud Console and retry after a few minutes."
        )

    lowered = error_message.lower()
    can_model_fallback = response.status_code in (400, 404) and ("enhanced" in lowered or "model" in lowered)
    decode_error_markers = (
        "bad sample rate",
        "16 bit",
        "bad encoding",
        "audio channel count",
        "encoding",
    )
    can_decode_fallback = response.status_code == 400 and any(marker in lowered for marker in decode_error_markers)

    if not can_model_fallback and not can_decode_fallback:
        raise RuntimeError(f"Speech-to-Text request failed: {error_message}")

    config = body.get("config")
    normalized_config = dict(config) if isinstance(config, dict) else {}
    if can_model_fallback:
        normalized_config.pop("useEnhanced", None)
        normalized_config.pop("model", None)
        normalized_config.pop("metadata", None)
        # Some models reject alternative_language_codes; retry without model-specific fields first.
        # If alternatives are still unsupported, Speech API will return a clear config error.
        # Keep alternatives by default because they are important for en/hi/te mixed traffic.
    if can_decode_fallback:
        normalized_config.pop("encoding", None)
        normalized_config.pop("sampleRateHertz", None)

    fallback_body = {
        **body,
        "config": normalized_config,
    }

    retry = client.post(url, json=fallback_body, headers=headers)
    if retry.status_code >= 400:
        raise RuntimeError(f"Speech-to-Text request failed: {_extract_speech_error(retry)}")

    payload = retry.json()
    if isinstance(payload, dict):
        return payload
    raise RuntimeError("Unexpected Speech-to-Text retry response format")


def _poll_long_running_operation(client: httpx.Client, headers: dict[str, str], operation_name: str) -> dict[str, object]:
    deadline = time.time() + max(30, int(settings.transcription_timeout_seconds))
    poll_interval = max(1, int(settings.transcription_poll_interval_seconds))
    normalized_name = operation_name.split("operations/", 1)[-1]
    operation_url = f"{GOOGLE_OPERATION_BASE_URL}/{normalized_name}"

    while time.time() < deadline:
        response = client.get(operation_url, headers=headers)
        if response.status_code >= 400:
            raise RuntimeError(f"Speech operation poll failed: {_extract_speech_error(response)}")

        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected speech operation response format")

        if payload.get("done"):
            error_payload = payload.get("error")
            if isinstance(error_payload, dict):
                message = str(error_payload.get("message") or "Speech operation failed")
                status = str(error_payload.get("status") or "")
                raise RuntimeError(f"Speech operation failed: {status} {message}".strip())

            response_payload = payload.get("response")
            if isinstance(response_payload, dict):
                return response_payload
            return {}

        time.sleep(poll_interval)

    raise TimeoutError("Speech long-running transcription timed out")


def _contains_language_tags(language_codes: list[str], required_tags: set[str]) -> bool:
    normalized_tags = {_normalize_language_tag(code) for code in language_codes if code}
    return required_tags.issubset(normalized_tags)


def _has_ascii_letters(text: str) -> bool:
    return bool(ASCII_ALPHA_RE.search(text or ""))


def _looks_telugu_english_mix(text: str) -> bool:
    normalized = text or ""
    return bool(TELUGU_RE.search(normalized) and _has_ascii_letters(normalized))


def _extract_alternative_confidence(alternative: dict[str, object]) -> float | None:
    raw_confidence = alternative.get("confidence")
    if raw_confidence is None:
        return None

    try:
        confidence = float(raw_confidence)
    except (TypeError, ValueError):
        return None

    if confidence < 0:
        return None
    return min(1.0, confidence)


def _score_transcript_alternative(transcript_text: str, confidence: float | None, prefer_code_mix: bool) -> float:
    normalized = " ".join((transcript_text or "").split())
    if not normalized:
        return float("-inf")

    tokens = normalized.split()
    token_count = len(tokens)
    unique_ratio = len({token.lower() for token in tokens}) / max(1, token_count)

    score = float(token_count) + (unique_ratio * 8.0)
    if confidence is not None:
        score += max(0.0, min(1.0, confidence)) * 25.0

    if prefer_code_mix:
        if _looks_telugu_english_mix(normalized):
            score += 18.0
        elif TELUGU_RE.search(normalized):
            score += 4.0

    return score


def _estimate_transcript_quality(
    transcript_text: str,
    avg_confidence: float | None,
    duration_seconds: float | None,
    prefer_code_mix: bool,
) -> float:
    score = _score_transcript_alternative(transcript_text, avg_confidence, prefer_code_mix)
    if score == float("-inf"):
        return -1.0

    normalized = " ".join((transcript_text or "").split())
    if duration_seconds is not None and duration_seconds > 0:
        chars_per_second = len(normalized) / max(1.0, float(duration_seconds))
        if chars_per_second < 2.8:
            score -= 6.0
        elif chars_per_second >= 4.0:
            score += 2.0

    if prefer_code_mix and not _looks_telugu_english_mix(normalized):
        score -= 3.0

    return score


def _extract_transcript(
    payload: dict[str, object],
    expected_language_codes: list[str] | None = None,
) -> tuple[str, str, float | None]:
    parts: list[str] = []
    confidence_values: list[float] = []
    language_hint = ""
    prefer_code_mix = _contains_language_tags(expected_language_codes or [], {"en", "te"})

    results = payload.get("results")
    if not isinstance(results, list):
        return "", "", None

    for item in results:
        if not isinstance(item, dict):
            continue

        if not language_hint:
            language_hint = str(item.get("languageCode") or "").strip()

        alternatives = item.get("alternatives")
        if not isinstance(alternatives, list) or not alternatives:
            continue

        best_text = ""
        best_confidence: float | None = None
        best_score = float("-inf")

        for alternative in alternatives:
            if not isinstance(alternative, dict):
                continue

            candidate_text = str(alternative.get("transcript") or "").strip()
            if not candidate_text:
                continue

            candidate_confidence = _extract_alternative_confidence(alternative)
            candidate_score = _score_transcript_alternative(
                candidate_text,
                candidate_confidence,
                prefer_code_mix,
            )
            if candidate_score > best_score:
                best_score = candidate_score
                best_text = candidate_text
                best_confidence = candidate_confidence

        if best_text:
            parts.append(best_text)
            if best_confidence is not None:
                confidence_values.append(best_confidence)

    average_confidence = (
        sum(confidence_values) / len(confidence_values)
        if confidence_values
        else None
    )

    return " ".join(parts).strip(), language_hint, average_confidence


def _reorder_language_codes(language_codes: list[str], preferred_tag: str) -> list[str]:
    preferred = [code for code in language_codes if _normalize_language_tag(code) == preferred_tag]
    remainder = [code for code in language_codes if _normalize_language_tag(code) != preferred_tag]

    deduped: list[str] = []
    for code in [*preferred, *remainder]:
        if code and code not in deduped:
            deduped.append(code)

    return deduped or list(language_codes)


def _should_use_long_running(duration_seconds: float | None, payload_size_bytes: int) -> bool:
    threshold = max(15, int(settings.transcription_long_running_threshold_seconds))
    if duration_seconds is not None and duration_seconds >= threshold:
        return True

    # Conservative fallback for unknown durations: larger payloads are usually long calls.
    return payload_size_bytes >= 900_000


def _should_try_code_mix_rescue(
    transcript_text: str,
    avg_confidence: float | None,
    duration_seconds: float | None,
    language_codes: list[str],
    force_short_request: bool,
) -> bool:
    if force_short_request:
        return False

    if not settings.google_speech_code_mix_rescue_enabled:
        return False

    if not _contains_language_tags(language_codes, {"en", "te"}):
        return False

    normalized = " ".join((transcript_text or "").split())
    if not normalized:
        return False

    # Already looks code-mixed; no need for an expensive rescue pass.
    if _looks_telugu_english_mix(normalized):
        return False

    min_chars = max(40, int(settings.google_speech_code_mix_min_chars))
    if len(normalized) < min_chars:
        return True

    threshold = float(settings.google_speech_code_mix_confidence_threshold)
    if avg_confidence is not None and avg_confidence < threshold:
        return True

    if duration_seconds is not None and duration_seconds >= 18:
        chars_per_second = len(normalized) / max(1.0, float(duration_seconds))
        if chars_per_second < 2.8:
            return True

    return False


def _pick_better_transcript_candidate(
    primary_text: str,
    primary_language_hint: str,
    primary_confidence: float | None,
    rescue_text: str,
    rescue_language_hint: str,
    rescue_confidence: float | None,
    duration_seconds: float | None,
    language_codes: list[str],
) -> tuple[str, str, float | None, bool]:
    prefer_code_mix = _contains_language_tags(language_codes, {"en", "te"})

    primary_score = _estimate_transcript_quality(
        primary_text,
        primary_confidence,
        duration_seconds,
        prefer_code_mix,
    )
    rescue_score = _estimate_transcript_quality(
        rescue_text,
        rescue_confidence,
        duration_seconds,
        prefer_code_mix,
    )

    # Require a measurable gain to avoid noisy switching between similar outputs.
    if rescue_score > (primary_score + 1.5):
        logger.info(
            "Using code-mix rescue transcript (score %.2f -> %.2f).",
            primary_score,
            rescue_score,
        )
        return rescue_text, rescue_language_hint, rescue_confidence, True

    return primary_text, primary_language_hint, primary_confidence, False


def _is_large_audio_retry_candidate(error_message: str) -> bool:
    lowered = (error_message or "").strip().lower()
    if not lowered:
        return False

    markers = (
        "inline audio exceeds duration limit",
        "request payload size exceeds the limit",
        "audio file exceeds active transcription payload limit",
        "normalized audio exceeds active transcription payload limit",
    )
    return any(marker in lowered for marker in markers)


def _strip_leading_speaker_tags(text: str) -> str:
    if not text:
        return ""

    cleaned_lines: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        cleaned = re.sub(
            r"(?i)^\s*(?:speaker\s*\d+|parent|caller|coordinator|agent|counselor|staff)\s*:\s*",
            "",
            line,
        ).strip()
        if cleaned:
            cleaned_lines.append(cleaned)

    return " ".join(cleaned_lines).strip()


def _normalize_romanized_transcript(text: str) -> str:
    # Keep output in English letters/punctuation only; drop non-Latin script characters.
    # Preserve newlines so that speaker-labeled transcripts retain their structure.
    raw = text or ""
    lines = raw.replace("\r\n", "\n").split("\n")
    cleaned_lines: list[str] = []
    for line in lines:
        cleaned = ASCII_TRANSCRIPT_RE.sub(" ", line)
        cleaned = " ".join(cleaned.split())
        if cleaned:
            cleaned_lines.append(cleaned)
    return "\n".join(cleaned_lines).strip()


def _should_try_google_speech_llm_rescue(result: TranscriptionResult) -> bool:
    if not settings.google_speech_llm_rescue_enabled:
        return False

    if not settings.gemini_api_key.strip():
        return False

    language_codes = _resolve_google_speech_language_codes()
    if not _contains_language_tags(language_codes, {"en", "te"}):
        return False

    normalized = _strip_leading_speaker_tags(result.text)
    if not normalized:
        return False

    if _looks_telugu_english_mix(normalized):
        return False

    if not _has_ascii_letters(normalized):
        return False

    min_chars = max(40, int(settings.google_speech_llm_rescue_min_chars))
    if len(normalized) < min_chars:
        return False

    confidence_threshold = float(settings.google_speech_code_mix_confidence_threshold)
    if result.confidence is not None and result.confidence >= confidence_threshold and len(normalized) >= (min_chars * 3):
        return False

    if result.duration_seconds is not None and result.duration_seconds > 0:
        chars_per_second = len(normalized) / max(1.0, float(result.duration_seconds))
        if chars_per_second >= 4.0 and len(normalized) >= (min_chars * 2):
            return False

    return True


def _pick_better_llm_audio_rescue_candidate(
    primary: TranscriptionResult,
    rescue: TranscriptionResult,
) -> tuple[TranscriptionResult, bool]:
    language_codes = _resolve_google_speech_language_codes()
    prefer_code_mix = _contains_language_tags(language_codes, {"en", "te"})

    primary_text = _strip_leading_speaker_tags(primary.text)
    rescue_text = _strip_leading_speaker_tags(rescue.text)

    primary_score = _estimate_transcript_quality(
        transcript_text=primary_text,
        avg_confidence=primary.confidence,
        duration_seconds=primary.duration_seconds,
        prefer_code_mix=prefer_code_mix,
    )
    rescue_score = _estimate_transcript_quality(
        transcript_text=rescue_text,
        avg_confidence=rescue.confidence,
        duration_seconds=rescue.duration_seconds,
        prefer_code_mix=prefer_code_mix,
    )

    margin = max(0.5, float(settings.google_speech_llm_rescue_score_margin))
    if rescue_score > (primary_score + margin):
        logger.info(
            "Using Gemini audio rescue transcript (score %.2f -> %.2f).",
            primary_score,
            rescue_score,
        )
        rescue.rescue_used = True
        rescue.rescue_provider = "gemini"
        rescue.rescue_reason = "llm_audio_rescue"
        return rescue, True

    return primary, False


def _resolve_speaker_labeling_provider() -> str:
    configured = (settings.transcription_speaker_labels_provider or "").strip().lower()
    if configured not in {"auto", "openai", "gemini"}:
        configured = "auto"

    has_openai = bool(settings.openai_api_key.strip())
    has_gemini = bool(settings.gemini_api_key.strip())

    if configured == "openai":
        return "openai" if has_openai else ""
    if configured == "gemini":
        return "gemini" if has_gemini else ""

    if has_openai:
        return "openai"
    if has_gemini:
        return "gemini"
    return ""


def _build_speaker_labeling_prompt(transcript_text: str, language: str) -> str:
    return (
        "You are formatting a school-admissions call transcript into speaker turns.\\n"
        "Return plain text only.\\n"
        "Use exactly these labels: Speaker 1: and Speaker 2:.\\n"
        "Put one turn per line.\\n"
        "Keep original words and language exactly as-is.\\n"
        "Do not translate, summarize, paraphrase, or correct grammar.\\n"
        "Do not remove meaningful content.\\n"
        "If uncertain, use best-effort alternation between Speaker 1 and Speaker 2.\\n"
        f"Detected language code: {language or 'unknown'}\\n"
        "Transcript:\\n"
        f"{transcript_text}"
    )


def _extract_openai_chat_text(payload: dict[str, object]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return ""

    message = first_choice.get("message")
    if not isinstance(message, dict):
        return ""

    content = message.get("content")
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if text:
                parts.append(text)
        return "\n".join(parts).strip()

    return ""


def _label_speakers_with_openai(prompt: str) -> str:
    if not settings.openai_api_key.strip():
        return ""

    body = {
        "model": settings.openai_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a transcript formatter. "
                    "Return only speaker-labeled transcript text with no extra commentary."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
    }
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }

    timeout_seconds = max(20, min(120, int(settings.transcription_timeout_seconds)))
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(OPENAI_CHAT_URL, json=body, headers=headers)
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, dict):
        return ""
    return _extract_openai_chat_text(payload)


def _label_speakers_with_gemini(prompt: str) -> str:
    api_key = settings.gemini_api_key.strip()
    if not api_key:
        return ""

    model = settings.gemini_model.strip() or settings.gemini_transcription_model.strip() or "gemini-1.5-flash"
    url = GEMINI_GENERATE_URL_TEMPLATE.format(model=model)
    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.0,
        },
    }

    timeout_seconds = max(20, min(120, int(settings.transcription_timeout_seconds)))
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(url, params={"key": api_key}, json=body)
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, dict):
        return ""
    return _extract_text_from_gemini_response(payload)


def _cleanup_labeled_transcript(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""

    if cleaned.lower().startswith("transcript:"):
        cleaned = cleaned.split(":", 1)[1].strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    lines: list[str] = []
    for line in cleaned.replace("\r\n", "\n").split("\n"):
        normalized_line = " ".join(line.split())
        if normalized_line:
            lines.append(normalized_line)

    if lines:
        return "\n".join(lines)
    return " ".join(cleaned.split())


def _count_speaker_tags(text: str) -> int:
    if not text:
        return 0
    return len(SPEAKER_TAG_RE.findall(text))


def _diarize_audio_with_gemini(
    audio_bytes: bytes,
    file_name: str,
    mime_type: str | None,
    raw_transcript: str,
    language: str,
) -> str:
    """Use Gemini with the actual audio to perform pitch/voice-based speaker diarization."""
    api_key = settings.gemini_api_key.strip()
    if not api_key:
        return ""

    model = settings.gemini_transcription_model.strip() or settings.gemini_model.strip() or "gemini-1.5-flash"
    resolved_mime = _mime_type_for_file(file_name, mime_type)

    prompt = (
        "You are an expert call transcript diarizer. You are given an audio recording of a phone call "
        "and its raw transcript text.\n"
        "Your task is to identify DIFFERENT SPEAKERS by their voice characteristics "
        "(pitch, tone, timbre, speaking style) and label each speaker's dialogue.\n\n"
        "CRITICAL RULES:\n"
        "1. Listen carefully to the audio to distinguish speakers by their VOICE, not by content.\n"
        "2. Label speakers as 'Speaker 1:', 'Speaker 2:', etc.\n"
        "3. Put each speaker turn on a NEW LINE.\n"
        "4. Include ALL dialogue — do NOT skip, summarize, or paraphrase any content.\n"
        "5. Keep the original words exactly as spoken.\n"
        "6. If the conversation has code-mixed languages (e.g. Telugu + English), keep the original language as-is.\n"
        "7. Return ONLY the speaker-labeled transcript. No timestamps, markdown, JSON, or explanations.\n\n"
        f"Detected language: {language or 'unknown'}\n\n"
        f"Raw transcript for reference:\n{raw_transcript[:8000]}\n\n"
        "Now listen to the audio and produce the speaker-diarized transcript:"
    )

    body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": resolved_mime,
                            "data": base64.b64encode(audio_bytes).decode("ascii"),
                        }
                    },
                ],
            }
        ],
        "generationConfig": {"temperature": 0.0},
    }

    url = GEMINI_GENERATE_URL_TEMPLATE.format(model=model)
    timeout_seconds = max(30, min(180, int(settings.transcription_timeout_seconds)))
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(url, params={"key": api_key}, json=body)
        if response.status_code >= 400:
            logger.warning("Gemini audio diarization request failed: %s", _extract_speech_error(response))
            return ""
        payload = response.json()

    if not isinstance(payload, dict):
        return ""

    raw_result = _extract_text_from_gemini_response(payload)
    cleaned = _cleanup_labeled_transcript(raw_result)
    return cleaned


def _maybe_apply_speaker_labeling(
    transcript_text: str,
    language: str,
    audio_bytes: bytes | None = None,
    audio_file_name: str | None = None,
    audio_mime_type: str | None = None,
) -> str:
    normalized = (transcript_text or "").strip()
    if not normalized:
        return ""

    if not settings.transcription_speaker_labels_enabled:
        return normalized

    if _count_speaker_tags(normalized) >= 2:
        return normalized

    max_chars = max(1000, int(settings.transcription_speaker_labels_max_chars))
    if len(normalized) > max_chars:
        logger.info(
            "Skipping speaker labeling for transcript (%d chars) over limit (%d chars).",
            len(normalized),
            max_chars,
        )
        return normalized

    # --- Audio-based diarization (preferred: uses pitch/voice to separate speakers) ---
    if audio_bytes and settings.gemini_api_key.strip():
        logger.info("Attempting audio-based speaker diarization with Gemini.")
        try:
            diarized = _diarize_audio_with_gemini(
                audio_bytes=audio_bytes,
                file_name=audio_file_name or "audio.flac",
                mime_type=audio_mime_type,
                raw_transcript=normalized,
                language=language,
            )
            if diarized and _count_speaker_tags(diarized) >= 2:
                logger.info("Audio-based diarization succeeded with %d speaker tags.", _count_speaker_tags(diarized))
                return diarized
            else:
                logger.warning("Audio-based diarization returned insufficient speaker tags; falling back.")
        except Exception:
            logger.exception("Audio-based diarization failed; falling back to text-based labeling.")

    # --- Fallback: text-only LLM speaker labeling ---
    provider = _resolve_speaker_labeling_provider()
    if not provider:
        return normalized

    prompt = _build_speaker_labeling_prompt(normalized, language)
    try:
        if provider == "gemini":
            raw_labeled = _label_speakers_with_gemini(prompt)
        else:
            raw_labeled = _label_speakers_with_openai(prompt)
    except Exception:
        logger.exception("Speaker labeling failed using provider '%s'; keeping raw transcript.", provider)
        return normalized

    labeled = _cleanup_labeled_transcript(raw_labeled)
    if not labeled:
        return normalized

    if _count_speaker_tags(labeled) < 2:
        logger.warning("Speaker labeling output had insufficient speaker tags; keeping raw transcript.")
        return normalized

    return labeled


def _finalize_transcription_result(
    transcript_text: str,
    language_hint: str,
    duration_seconds: float | None,
    provider: str,
    rescue_used: bool = False,
    rescue_provider: str | None = None,
    rescue_reason: str | None = None,
    audio_bytes: bytes | None = None,
    audio_file_name: str | None = None,
    audio_mime_type: str | None = None,
) -> TranscriptionResult:
    normalized_transcript = _normalize_romanized_transcript(transcript_text or "")
    if not normalized_transcript:
        return TranscriptionResult(
            text="IGNORE",
            language="en",
            duration_seconds=duration_seconds,
            provider=provider,
            rescue_used=rescue_used,
            rescue_provider=rescue_provider,
            rescue_reason=rescue_reason,
        )

    normalized_language = _normalize_language_tag(language_hint)
    if normalized_language == "unknown":
        normalized_language = detect_language_from_text(normalized_transcript)

    allowed_languages = {item.lower() for item in settings.allowed_transcript_languages}
    if normalized_language not in allowed_languages:
        raise UnsupportedLanguageError(f"Unsupported language detected: {normalized_language}")

    finalized_text = _maybe_apply_speaker_labeling(
        normalized_transcript,
        normalized_language,
        audio_bytes=audio_bytes,
        audio_file_name=audio_file_name,
        audio_mime_type=audio_mime_type,
    )
    if not finalized_text:
        finalized_text = normalized_transcript

    return TranscriptionResult(
        text=finalized_text,
        language=normalized_language,
        duration_seconds=duration_seconds,
        provider=provider,
        rescue_used=rescue_used,
        rescue_provider=rescue_provider,
        rescue_reason=rescue_reason,
    )


def _build_gemini_transcription_prompt(language_codes: list[str]) -> str:
    expected_languages = ", ".join(language_codes[:4]) if language_codes else "en-US, te-IN"
    return (
        "Transcribe this call audio accurately with speaker diarization.\n"
        "Identify different speakers by their voice characteristics (pitch, tone, timbre).\n"
        "Label each speaker's dialogue as 'Speaker 1:', 'Speaker 2:', etc.\n"
        "Put each speaker turn on a new line.\n"
        "Include ALL dialogue — do NOT skip, summarize, or paraphrase any content.\n"
        "Keep the original words exactly as spoken.\n"
        f"Expected languages: {expected_languages}.\n"
        "Return ONLY the speaker-labeled transcript. No timestamps, markdown, JSON, or explanations.\n"
        "If there is no intelligible speech, return exactly: EMPTY_TRANSCRIPT"
    )


def _extract_text_from_gemini_response(payload: dict[str, object]) -> str:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        return ""

    collected_parts: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        content = candidate.get("content")
        if not isinstance(content, dict):
            continue

        parts = content.get("parts")
        if not isinstance(parts, list):
            continue

        for part in parts:
            if not isinstance(part, dict):
                continue
            text = str(part.get("text") or "").strip()
            if text:
                collected_parts.append(text)

        if collected_parts:
            break

    combined = " ".join(collected_parts).strip()
    if combined.lower().startswith("transcript:"):
        combined = combined.split(":", 1)[1].strip()

    if combined.startswith("```") and combined.endswith("```"):
        combined = combined.strip("`").strip()

    return combined


def _transcribe_with_gemini(
    audio_bytes: bytes,
    file_name: str,
    mime_type: str | None,
    duration_seconds: float | None,
) -> TranscriptionResult:
    api_key = settings.gemini_api_key.strip()
    if not api_key:
        raise TranscriptionConfigurationError(
            "Gemini transcription requires GEMINI_API_KEY. "
            "Set GEMINI_API_KEY or switch TRANSCRIPTION_PROVIDER=google_speech."
        )

    max_inline_bytes = max(1, int(settings.gemini_transcription_inline_max_mb)) * 1024 * 1024
    if len(audio_bytes) > max_inline_bytes:
        raise ValueError(
            "Audio exceeds GEMINI_TRANSCRIPTION_INLINE_MAX_MB "
            f"({settings.gemini_transcription_inline_max_mb} MB)."
        )

    model = settings.gemini_transcription_model.strip() or settings.gemini_model.strip() or "gemini-1.5-flash"
    language_codes = _resolve_google_speech_language_codes()
    prompt = _build_gemini_transcription_prompt(language_codes)

    body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": _mime_type_for_file(file_name, mime_type),
                            "data": base64.b64encode(audio_bytes).decode("ascii"),
                        }
                    },
                ],
            }
        ],
        "generationConfig": {"temperature": 0.0},
    }

    url = GEMINI_GENERATE_URL_TEMPLATE.format(model=model)
    with httpx.Client(timeout=max(20, settings.transcription_timeout_seconds)) as client:
        response = client.post(url, params={"key": api_key}, json=body)
        if response.status_code >= 400:
            error_message = _extract_speech_error(response)
            lowered = error_message.lower()
            if response.status_code in (429, 503) or "resource_exhausted" in lowered or "quota exceeded" in lowered:
                raise TranscriptionConfigurationError(
                    "Gemini transcription quota is exhausted or unavailable for this API key/model. "
                    "Enable billing/quota for Gemini API or use another key/model."
                )
            if response.status_code == 404 and ("models/" in lowered or "not found" in lowered):
                raise TranscriptionConfigurationError(
                    f"Gemini transcription model '{model}' is unavailable for this API key. "
                    "Set GEMINI_TRANSCRIPTION_MODEL to a supported model for your account."
                )
            raise RuntimeError(f"Gemini transcription request failed: {error_message}")

        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected Gemini transcription response format")

    transcript_text = _extract_text_from_gemini_response(payload)
    if transcript_text.upper() == "EMPTY_TRANSCRIPT":
        raise ValueError("Gemini returned no transcript")

    return _finalize_transcription_result(
        transcript_text=transcript_text,
        language_hint="",
        duration_seconds=duration_seconds,
        provider="gemini",
        audio_bytes=audio_bytes,
        audio_file_name=file_name,
        audio_mime_type=mime_type,
    )


def _transcribe_with_google_speech_payload(
    audio_bytes: bytes,
    file_name: str,
    mime_type: str | None,
    duration_seconds: float | None,
    access_token: str,
    force_short_request: bool = False,
) -> tuple[str, str, float | None, bool]:
    encoding, sample_rate_hz = _speech_decoding_for_file(audio_bytes, file_name, mime_type)

    language_codes = _resolve_google_speech_language_codes()
    audio_content = base64.b64encode(audio_bytes).decode("ascii")
    config = _build_recognition_config(language_codes, encoding, sample_rate_hz)

    body = {
        "config": config,
        "audio": {"content": audio_content},
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    use_long_running = False if force_short_request else _should_use_long_running(duration_seconds, len(audio_bytes))

    with httpx.Client(timeout=max(15, settings.transcription_timeout_seconds)) as client:
        if use_long_running:
            operation = _request_with_config_fallback(client, SPEECH_LONG_RUNNING_URL, body, headers)
            operation_name = str(operation.get("name") or "").strip()
            if not operation_name:
                raise RuntimeError("Speech operation did not return an operation name")
            payload = _poll_long_running_operation(client, headers, operation_name)
        else:
            payload = _request_with_config_fallback(client, SPEECH_RECOGNIZE_URL, body, headers)

        transcript_text, language_hint, avg_confidence = _extract_transcript(
            payload,
            expected_language_codes=language_codes,
        )
        if not transcript_text and not use_long_running and not force_short_request:
            operation = _request_with_config_fallback(client, SPEECH_LONG_RUNNING_URL, body, headers)
            operation_name = str(operation.get("name") or "").strip()
            if not operation_name:
                raise RuntimeError("Speech operation did not return an operation name")
            long_payload = _poll_long_running_operation(client, headers, operation_name)
            transcript_text, language_hint, avg_confidence = _extract_transcript(
                long_payload,
                expected_language_codes=language_codes,
            )

        used_code_mix_rescue = False

        if _should_try_code_mix_rescue(
            transcript_text=transcript_text,
            avg_confidence=avg_confidence,
            duration_seconds=duration_seconds,
            language_codes=language_codes,
            force_short_request=force_short_request,
        ):
            rescue_language_codes = _reorder_language_codes(language_codes, preferred_tag="te")
            if rescue_language_codes != language_codes:
                logger.info(
                    "Retrying Speech-to-Text with Telugu-priority language order for code-mix rescue."
                )
                rescue_config = _build_recognition_config(
                    rescue_language_codes,
                    encoding,
                    sample_rate_hz,
                )
                rescue_body = {
                    "config": rescue_config,
                    "audio": {"content": audio_content},
                }

                if use_long_running:
                    rescue_operation = _request_with_config_fallback(
                        client,
                        SPEECH_LONG_RUNNING_URL,
                        rescue_body,
                        headers,
                    )
                    rescue_operation_name = str(rescue_operation.get("name") or "").strip()
                    if not rescue_operation_name:
                        raise RuntimeError("Speech operation did not return an operation name")
                    rescue_payload = _poll_long_running_operation(client, headers, rescue_operation_name)
                else:
                    rescue_payload = _request_with_config_fallback(
                        client,
                        SPEECH_RECOGNIZE_URL,
                        rescue_body,
                        headers,
                    )

                rescue_text, rescue_language_hint, rescue_confidence = _extract_transcript(
                    rescue_payload,
                    expected_language_codes=rescue_language_codes,
                )

                if not rescue_text and not use_long_running:
                    rescue_operation = _request_with_config_fallback(
                        client,
                        SPEECH_LONG_RUNNING_URL,
                        rescue_body,
                        headers,
                    )
                    rescue_operation_name = str(rescue_operation.get("name") or "").strip()
                    if not rescue_operation_name:
                        raise RuntimeError("Speech operation did not return an operation name")
                    rescue_long_payload = _poll_long_running_operation(client, headers, rescue_operation_name)
                    rescue_text, rescue_language_hint, rescue_confidence = _extract_transcript(
                        rescue_long_payload,
                        expected_language_codes=rescue_language_codes,
                    )

                if rescue_text:
                    transcript_text, language_hint, avg_confidence, used_code_mix_rescue = _pick_better_transcript_candidate(
                        primary_text=transcript_text,
                        primary_language_hint=language_hint,
                        primary_confidence=avg_confidence,
                        rescue_text=rescue_text,
                        rescue_language_hint=rescue_language_hint,
                        rescue_confidence=rescue_confidence,
                        duration_seconds=duration_seconds,
                        language_codes=language_codes,
                    )

    return transcript_text, language_hint, avg_confidence, used_code_mix_rescue


def _transcribe_with_google_speech(
    audio_bytes: bytes,
    file_name: str,
    mime_type: str | None,
    duration_seconds: float | None,
    access_token: str,
) -> TranscriptionResult:
    transcript_text, language_hint, avg_confidence, used_code_mix_rescue = _transcribe_with_google_speech_payload(
        audio_bytes=audio_bytes,
        file_name=file_name,
        mime_type=mime_type,
        duration_seconds=duration_seconds,
        access_token=access_token,
    )

    result = _finalize_transcription_result(
        transcript_text=transcript_text,
        language_hint=language_hint,
        duration_seconds=duration_seconds,
        provider="google_speech",
        rescue_used=used_code_mix_rescue,
        rescue_provider="google_speech" if used_code_mix_rescue else None,
        rescue_reason="code_mix_language_retry" if used_code_mix_rescue else None,
        audio_bytes=audio_bytes,
        audio_file_name=file_name,
        audio_mime_type=mime_type,
    )
    result.confidence = avg_confidence
    return result


def _transcribe_with_google_speech_chunked(
    audio_bytes: bytes,
    file_name: str,
    access_token: str,
    max_bytes: int,
) -> TranscriptionResult:
    max_mb = max_bytes // (1024 * 1024)
    if not can_normalize_audio_locally():
        raise ValueError(f"Audio file exceeds active transcription payload limit ({max_mb} MB)")

    logger.info(
        "Using chunked transcription fallback for '%s' (%d bytes).",
        file_name,
        len(audio_bytes),
    )

    chunk_seconds = max(15, int(settings.transcription_chunk_target_seconds))
    chunks: list[tuple[bytes, float | None]] = []

    for _ in range(4):
        chunks = _split_audio_into_flac_chunks(audio_bytes, file_name, chunk_seconds)
        if chunks and all(len(chunk_bytes) <= max_bytes for chunk_bytes, _ in chunks):
            break
        chunk_seconds = max(10, chunk_seconds // 2)

    if not chunks:
        raise RuntimeError("Unable to split audio into chunks for transcription")

    logger.info("Split '%s' into %d chunk(s) at %ds target window.", file_name, len(chunks), chunk_seconds)

    transcript_parts: list[str] = []
    language_votes: dict[str, int] = {}
    total_duration_seconds = 0.0
    has_duration = False
    confidence_values: list[float] = []
    used_code_mix_rescue = False

    for index, (chunk_bytes, chunk_duration) in enumerate(chunks, start=1):
        if len(chunk_bytes) > max_bytes:
            raise ValueError(f"Audio chunk exceeds active transcription payload limit ({max_mb} MB)")

        chunk_name = f"{Path(file_name).stem}_chunk_{index}.flac"
        chunk_text, chunk_language, chunk_confidence, chunk_used_code_mix_rescue = _transcribe_with_google_speech_payload(
            audio_bytes=chunk_bytes,
            file_name=chunk_name,
            mime_type="audio/flac",
            duration_seconds=chunk_duration,
            access_token=access_token,
            force_short_request=True,
        )

        normalized_chunk_text = " ".join((chunk_text or "").split())
        if not normalized_chunk_text:
            continue

        transcript_parts.append(normalized_chunk_text)
        normalized_chunk_language = _normalize_language_tag(chunk_language)
        if normalized_chunk_language != "unknown":
            language_votes[normalized_chunk_language] = language_votes.get(normalized_chunk_language, 0) + 1

        if chunk_duration is not None:
            total_duration_seconds += float(chunk_duration)
            has_duration = True

        if chunk_confidence is not None:
            confidence_values.append(float(chunk_confidence))
        used_code_mix_rescue = used_code_mix_rescue or chunk_used_code_mix_rescue

    combined_text = _merge_chunk_transcripts(transcript_parts)
    if not combined_text:
        raise ValueError("Transcription returned no transcript")

    primary_language = ""
    if language_votes:
        primary_language = max(language_votes.items(), key=lambda item: item[1])[0]

    result = _finalize_transcription_result(
        transcript_text=combined_text,
        language_hint=primary_language,
        duration_seconds=total_duration_seconds if has_duration else None,
        provider="google_speech",
        rescue_used=used_code_mix_rescue,
        rescue_provider="google_speech" if used_code_mix_rescue else None,
        rescue_reason="code_mix_language_retry" if used_code_mix_rescue else None,
        audio_bytes=audio_bytes,
        audio_file_name=file_name,
        audio_mime_type=None,
    )
    if confidence_values:
        result.confidence = sum(confidence_values) / len(confidence_values)

    return result


def transcribe_audio_bytes(
    audio_bytes: bytes,
    file_name: str,
    mime_type: str | None = None,
    access_token: str | None = None,
) -> TranscriptionResult:
    if not audio_bytes:
        raise ValueError("Audio payload is empty")

    provider = _resolve_transcription_provider()
    max_bytes = get_transcription_max_audio_bytes()
    max_mb = max_bytes // (1024 * 1024)

    normalized_bytes, normalized_name, duration_seconds = _normalize_audio_with_ffmpeg(audio_bytes, file_name)

    if provider == "gemini":
        if len(normalized_bytes) > max_bytes:
            raise ValueError(
                f"Normalized audio exceeds active transcription payload limit ({max_mb} MB); "
                "increase limit or disable TRANSCRIPTION_NORMALIZE_AUDIO"
            )
        return _transcribe_with_gemini(
            audio_bytes=normalized_bytes,
            file_name=normalized_name,
            mime_type=mime_type,
            duration_seconds=duration_seconds,
        )

    if not settings.google_service_account_json.strip() and not settings.google_service_account_file.strip():
        raise ValueError(
            "Google Speech transcription requires service-account credentials. "
            "Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_FILE, "
            "or switch TRANSCRIPTION_PROVIDER=gemini."
        )

    active_token = access_token or get_google_access_token(scopes=[CLOUD_PLATFORM_SCOPE])

    google_result: TranscriptionResult
    if len(normalized_bytes) > max_bytes:
        if can_normalize_audio_locally():
            logger.info("Audio '%s' exceeds inline payload limit; retrying with chunked fallback.", normalized_name)
            google_result = _transcribe_with_google_speech_chunked(
                audio_bytes=normalized_bytes,
                file_name=normalized_name,
                access_token=active_token,
                max_bytes=max_bytes,
            )
        else:
            raise ValueError(f"Audio file exceeds active transcription payload limit ({max_mb} MB)")
    else:
        try:
            google_result = _transcribe_with_google_speech(
                audio_bytes=normalized_bytes,
                file_name=normalized_name,
                mime_type=mime_type,
                duration_seconds=duration_seconds,
                access_token=active_token,
            )
        except RuntimeError as exc:
            if can_normalize_audio_locally() and _is_large_audio_retry_candidate(str(exc)):
                logger.info(
                    "Speech request for '%s' hit inline limit (%s); retrying with chunked fallback.",
                    normalized_name,
                    str(exc),
                )
                google_result = _transcribe_with_google_speech_chunked(
                    audio_bytes=normalized_bytes,
                    file_name=normalized_name,
                    access_token=active_token,
                    max_bytes=max_bytes,
                )
            else:
                raise

    if _should_try_google_speech_llm_rescue(google_result):
        logger.info("Trying Gemini audio rescue for likely weak mixed-language transcript.")
        try:
            llm_rescue_result = _transcribe_with_gemini(
                audio_bytes=normalized_bytes,
                file_name=normalized_name,
                mime_type=mime_type,
                duration_seconds=duration_seconds,
            )
        except Exception:
            logger.exception("Gemini audio rescue failed; keeping Google Speech transcript.")
        else:
            google_result, _ = _pick_better_llm_audio_rescue_candidate(google_result, llm_rescue_result)

    return google_result
