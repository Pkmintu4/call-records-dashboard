import json

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    database_url: str = "sqlite:///./call_records.db"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])

    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""
    google_drive_folder_id: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/google/callback"
    transcript_filename_keyword: str = "transcript"
    transcript_min_chars: int = 30
    ingest_default_limit: int = 100
    
    auto_ingest_enabled: bool = True
    auto_ingest_interval_seconds: int = 300

    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: object) -> str:
        raw = str(value or "").strip()
        if not raw:
            return "sqlite:///./call_records.db"
        if raw.startswith("postgres://"):
            return "postgresql+psycopg2://" + raw[len("postgres://") :]
        if raw.startswith("postgresql://"):
            return "postgresql+psycopg2://" + raw[len("postgresql://") :]
        return raw

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> list[str]:
        if isinstance(value, list):
            origins = [str(item).strip() for item in value if str(item).strip()]
        elif isinstance(value, str):
            raw = value.strip()
            if not raw:
                origins = []
            elif raw.startswith("["):
                parsed = json.loads(raw)
                origins = [str(item).strip() for item in parsed if str(item).strip()]
            else:
                origins = [item.strip() for item in raw.split(",") if item.strip()]
        else:
            origins = []

        for local_origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
            if local_origin not in origins:
                origins.append(local_origin)
        return origins


settings = Settings()
