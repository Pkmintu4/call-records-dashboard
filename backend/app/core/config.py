import json

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    database_url: str = "postgresql+psycopg2://neondb_owner:npg_68tpDUEekCWT@ep-flat-mode-amli39xq-pooler.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    cors_origins: list[str] = Field(default_factory=lambda: [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5176",
        "http://127.0.0.1:5176"
    ])

    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""
    google_service_account_json: str = ""
    google_service_account_file: str = ""
    google_service_account_subject: str = ""
    google_drive_folder_id: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/google/callback"
    drive_scan_recursive: bool = True
    drive_scan_max_folders: int = 200
    transcript_filename_keyword: str = "transcript"
    transcript_min_chars: int = 30
    ingest_default_limit: int = 100
    ingest_force_audio_only: bool = True
    audio_ingest_enabled: bool = True
    allowed_transcript_languages: list[str] = Field(default_factory=lambda: ["en", "te"])
    google_speech_language_codes: list[str] = Field(default_factory=lambda: ["en-IN", "te-IN"])
    google_speech_model: str = "phone_call"
    google_speech_use_enhanced: bool = True
    google_speech_code_mix_rescue_enabled: bool = True
    google_speech_code_mix_confidence_threshold: float = 0.72
    google_speech_code_mix_min_chars: int = 120
    google_speech_llm_rescue_enabled: bool = True
    google_speech_llm_rescue_min_chars: int = 120
    google_speech_llm_rescue_score_margin: float = 1.5
    transcription_provider: str = "google_speech"
    transcription_timeout_seconds: int = 180
    transcription_poll_interval_seconds: int = 2
    transcription_long_running_threshold_seconds: int = 55
    transcription_normalize_audio: bool = True
    transcription_denoise_enabled: bool = True
    transcription_chunk_target_seconds: int = 30
    transcription_chunk_overlap_seconds: int = 2
    transcription_max_audio_mb: int = 25
    transcription_speaker_labels_enabled: bool = True
    transcription_speaker_labels_provider: str = "auto"
    transcription_speaker_labels_max_chars: int = 18000
    gemini_transcription_model: str = "gemini-1.5-flash"
    gemini_transcription_inline_max_mb: int = 18
    
    auto_ingest_enabled: bool = True
    auto_ingest_interval_seconds: int = 300

    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    gemini_enabled: bool = False
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"
    gemini_timeout_seconds: int = 60

    @staticmethod
    def _parse_string_list(value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]

        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            if raw.startswith("["):
                parsed = json.loads(raw)
                return [str(item).strip() for item in parsed if str(item).strip()]
            return [item.strip() for item in raw.split(",") if item.strip()]

        return []

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: object) -> str:
        raw = str(value or "").strip()
        if not raw:
            return "postgresql+psycopg2://postgres:postgres@localhost:5432/call_records"
        if raw.startswith("postgres://"):
            return "postgresql+psycopg2://" + raw[len("postgres://") :]
        if raw.startswith("postgresql://"):
            return "postgresql+psycopg2://" + raw[len("postgresql://") :]
        return raw

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> list[str]:
        origins = cls._parse_string_list(value)

        for local_origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
            if local_origin not in origins:
                origins.append(local_origin)
        return origins

    @field_validator("allowed_transcript_languages", mode="before")
    @classmethod
    def parse_allowed_transcript_languages(cls, value: object) -> list[str]:
        languages = [item.lower() for item in cls._parse_string_list(value)]
        normalized: list[str] = []
        for item in languages:
            if item in {"en", "te"} and item not in normalized:
                normalized.append(item)
        return normalized or ["en", "te"]

    @field_validator("google_speech_language_codes", mode="before")
    @classmethod
    def parse_google_speech_language_codes(cls, value: object) -> list[str]:
        language_codes = cls._parse_string_list(value)
        if not language_codes:
            return ["en-IN", "te-IN"]

        # Enforce en-IN as required primary recognition language.
        deduped: list[str] = ["en-IN"]
        for code in language_codes:
            normalized = str(code).strip()
            if not normalized or normalized == "en-IN":
                continue
            if normalized.lower().startswith("hi"):
                continue
            if normalized not in deduped:
                deduped.append(normalized)
        return deduped

    @field_validator("google_speech_code_mix_confidence_threshold", mode="before")
    @classmethod
    def parse_google_speech_code_mix_confidence_threshold(cls, value: object) -> float:
        try:
            threshold = float(value)
        except (TypeError, ValueError):
            threshold = 0.72
        return max(0.1, min(0.99, threshold))

    @field_validator("google_speech_llm_rescue_score_margin", mode="before")
    @classmethod
    def parse_google_speech_llm_rescue_score_margin(cls, value: object) -> float:
        try:
            margin = float(value)
        except (TypeError, ValueError):
            margin = 1.5
        return max(0.2, min(8.0, margin))

    @field_validator("transcription_provider", mode="before")
    @classmethod
    def parse_transcription_provider(cls, value: object) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"google_speech", "gemini"}:
            return normalized
        return "google_speech"

    @field_validator("transcription_speaker_labels_provider", mode="before")
    @classmethod
    def parse_transcription_speaker_labels_provider(cls, value: object) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"auto", "openai", "gemini"}:
            return normalized
        return "auto"


settings = Settings()
