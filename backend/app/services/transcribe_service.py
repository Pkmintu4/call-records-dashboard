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
    "en": "en-US",
    "te": "te-IN",
    "hi": "hi-IN",
}
DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
TELUGU_RE = re.compile(r"[\u0C00-\u0C7F]")
logger = logging.getLogger(__name__)
NON_WORD_RE = re.compile(r"[^a-z0-9]+")


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
        configured = ["en-US", "hi-IN", "te-IN"]

    allowed_languages = {str(item).strip().lower() for item in settings.allowed_transcript_languages if str(item).strip()}
    if not allowed_languages:
        return configured

    filtered = [code for code in configured if _normalize_language_tag(code) in allowed_languages]
    if filtered:
        return filtered

    fallback: list[str] = []
    for language_tag in ("en", "te", "hi"):
        if language_tag in allowed_languages:
            code = DEFAULT_LANGUAGE_CODE_BY_TAG.get(language_tag)
            if code and code not in fallback:
                fallback.append(code)

    return fallback or configured


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


def _extract_transcript(payload: dict[str, object]) -> tuple[str, str]:
    parts: list[str] = []
    language_hint = ""

    results = payload.get("results")
    if not isinstance(results, list):
        return "", ""

    for item in results:
        if not isinstance(item, dict):
            continue

        if not language_hint:
            language_hint = str(item.get("languageCode") or "").strip()

        alternatives = item.get("alternatives")
        if not isinstance(alternatives, list) or not alternatives:
            continue

        best = alternatives[0]
        if not isinstance(best, dict):
            continue

        transcript_part = str(best.get("transcript") or "").strip()
        if transcript_part:
            parts.append(transcript_part)

    return " ".join(parts).strip(), language_hint


def _should_use_long_running(duration_seconds: float | None, payload_size_bytes: int) -> bool:
    threshold = max(15, int(settings.transcription_long_running_threshold_seconds))
    if duration_seconds is not None and duration_seconds >= threshold:
        return True

    # Conservative fallback for unknown durations: larger payloads are usually long calls.
    return payload_size_bytes >= 900_000


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


def _finalize_transcription_result(
    transcript_text: str,
    language_hint: str,
    duration_seconds: float | None,
) -> TranscriptionResult:
    normalized_transcript = " ".join((transcript_text or "").split())
    if not normalized_transcript:
        raise ValueError("Transcription returned no transcript")

    normalized_language = _normalize_language_tag(language_hint)
    if normalized_language == "unknown":
        normalized_language = detect_language_from_text(normalized_transcript)

    allowed_languages = {item.lower() for item in settings.allowed_transcript_languages}
    if normalized_language not in allowed_languages:
        raise UnsupportedLanguageError(f"Unsupported language detected: {normalized_language}")

    return TranscriptionResult(
        text=normalized_transcript,
        language=normalized_language,
        duration_seconds=duration_seconds,
    )


def _build_gemini_transcription_prompt(language_codes: list[str]) -> str:
    expected_languages = ", ".join(language_codes[:4]) if language_codes else "en-US, te-IN"
    return (
        "Transcribe this call audio accurately.\\n"
        "Return only plain transcript text.\\n"
        "Do not include speaker labels, timestamps, markdown, JSON, or explanations.\\n"
        f"Expected languages: {expected_languages}.\\n"
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
    )


def _transcribe_with_google_speech_payload(
    audio_bytes: bytes,
    file_name: str,
    mime_type: str | None,
    duration_seconds: float | None,
    access_token: str,
    force_short_request: bool = False,
) -> tuple[str, str]:
    encoding, sample_rate_hz = _speech_decoding_for_file(audio_bytes, file_name, mime_type)

    language_codes = _resolve_google_speech_language_codes()
    config = _build_recognition_config(language_codes, encoding, sample_rate_hz)

    body = {
        "config": config,
        "audio": {"content": base64.b64encode(audio_bytes).decode("ascii")},
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

        transcript_text, language_hint = _extract_transcript(payload)
        if not transcript_text and not use_long_running and not force_short_request:
            operation = _request_with_config_fallback(client, SPEECH_LONG_RUNNING_URL, body, headers)
            operation_name = str(operation.get("name") or "").strip()
            if not operation_name:
                raise RuntimeError("Speech operation did not return an operation name")
            long_payload = _poll_long_running_operation(client, headers, operation_name)
            transcript_text, language_hint = _extract_transcript(long_payload)

    return transcript_text, language_hint


def _transcribe_with_google_speech(
    audio_bytes: bytes,
    file_name: str,
    mime_type: str | None,
    duration_seconds: float | None,
    access_token: str,
) -> TranscriptionResult:
    transcript_text, language_hint = _transcribe_with_google_speech_payload(
        audio_bytes=audio_bytes,
        file_name=file_name,
        mime_type=mime_type,
        duration_seconds=duration_seconds,
        access_token=access_token,
    )

    return _finalize_transcription_result(
        transcript_text=transcript_text,
        language_hint=language_hint,
        duration_seconds=duration_seconds,
    )


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

    for index, (chunk_bytes, chunk_duration) in enumerate(chunks, start=1):
        if len(chunk_bytes) > max_bytes:
            raise ValueError(f"Audio chunk exceeds active transcription payload limit ({max_mb} MB)")

        chunk_name = f"{Path(file_name).stem}_chunk_{index}.flac"
        chunk_text, chunk_language = _transcribe_with_google_speech_payload(
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

    combined_text = _merge_chunk_transcripts(transcript_parts)
    if not combined_text:
        raise ValueError("Transcription returned no transcript")

    primary_language = ""
    if language_votes:
        primary_language = max(language_votes.items(), key=lambda item: item[1])[0]

    return _finalize_transcription_result(
        transcript_text=combined_text,
        language_hint=primary_language,
        duration_seconds=total_duration_seconds if has_duration else None,
    )


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

    if len(normalized_bytes) > max_bytes:
        if can_normalize_audio_locally():
            logger.info("Audio '%s' exceeds inline payload limit; retrying with chunked fallback.", normalized_name)
            return _transcribe_with_google_speech_chunked(
                audio_bytes=normalized_bytes,
                file_name=normalized_name,
                access_token=active_token,
                max_bytes=max_bytes,
            )
        raise ValueError(f"Audio file exceeds active transcription payload limit ({max_mb} MB)")

    try:
        return _transcribe_with_google_speech(
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
            return _transcribe_with_google_speech_chunked(
                audio_bytes=normalized_bytes,
                file_name=normalized_name,
                access_token=active_token,
                max_bytes=max_bytes,
            )
        raise
