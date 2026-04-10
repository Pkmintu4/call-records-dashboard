import json
from pathlib import Path
from urllib.parse import urlencode

from google.auth.transport.requests import Request
from google.oauth2 import service_account
import httpx

from app.core.config import settings


TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


def is_service_account_mode() -> bool:
    return bool(settings.google_service_account_json.strip() or settings.google_service_account_file.strip())


def _extract_google_token_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return text or f"HTTP {response.status_code}"

    error = payload.get("error")
    description = payload.get("error_description")
    if error and description:
        return f"{error}: {description}"
    if error:
        return str(error)
    if description:
        return str(description)
    return str(payload)


def _resolve_service_account_info() -> dict[str, str] | None:
    raw_json = settings.google_service_account_json.strip()
    raw_file = settings.google_service_account_file.strip()

    if not raw_json and not raw_file:
        return None

    if raw_json:
        try:
            info = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON must be valid JSON") from exc
    else:
        file_path = Path(raw_file)
        candidates = [file_path]
        if not file_path.is_absolute():
            candidates.append(Path.cwd() / file_path)

        target: Path | None = None
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                target = candidate
                break

        if target is None:
            raise ValueError(f"Service account file not found: {raw_file}")

        try:
            info = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in service account file: {target}") from exc

    private_key = info.get("private_key")
    if isinstance(private_key, str):
        info["private_key"] = private_key.replace("\\n", "\n")

    return info


def _get_service_account_access_token(scopes: list[str]) -> str | None:
    info = _resolve_service_account_info()
    if info is None:
        return None

    credentials = service_account.Credentials.from_service_account_info(
        info,
        scopes=scopes,
    )

    subject = settings.google_service_account_subject.strip()
    if subject:
        credentials = credentials.with_subject(subject)

    credentials.refresh(Request())
    access_token = credentials.token
    if not access_token:
        raise RuntimeError("Failed to obtain Google access token from service account credentials")
    return access_token


def get_google_access_token(scopes: list[str] | None = None) -> str:
    active_scopes = scopes or [DRIVE_READONLY_SCOPE]

    service_account_token = _get_service_account_access_token(active_scopes)
    if service_account_token:
        return service_account_token

    client_id = settings.google_client_id.strip()
    client_secret = settings.google_client_secret.strip()
    refresh_token = settings.google_refresh_token.strip()

    if not client_id or not client_secret or not refresh_token:
        raise ValueError(
            "Missing Google auth credentials. Configure service account "
            "(GOOGLE_SERVICE_ACCOUNT_JSON/FILE) or OAuth refresh token "
            "(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN)."
        )

    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    with httpx.Client(timeout=20) as client:
        response = client.post(TOKEN_URL, data=payload)
        if response.status_code >= 400:
            error_message = _extract_google_token_error(response)
            raise RuntimeError(f"Google token exchange failed ({response.status_code}): {error_message}")
        token_data = response.json()

    access_token = token_data.get("access_token")
    if not access_token:
        raise RuntimeError("Failed to obtain Google access token")
    return access_token


def build_google_auth_url(state: str) -> str:
    if not settings.google_client_id:
        raise ValueError("Missing Google client id")

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": DRIVE_READONLY_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code_for_tokens(code: str) -> dict[str, str]:
    client_id = settings.google_client_id.strip()
    client_secret = settings.google_client_secret.strip()

    if not client_id or not client_secret:
        raise ValueError("Missing Google OAuth client credentials")

    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code.strip(),
        "grant_type": "authorization_code",
        "redirect_uri": settings.google_redirect_uri,
    }

    with httpx.Client(timeout=20) as client:
        response = client.post(TOKEN_URL, data=payload)
        if response.status_code >= 400:
            error_message = _extract_google_token_error(response)
            raise RuntimeError(f"Google code exchange failed ({response.status_code}): {error_message}")
        token_data = response.json()

    return {
        "access_token": token_data.get("access_token", ""),
        "refresh_token": token_data.get("refresh_token", ""),
        "token_type": token_data.get("token_type", "Bearer"),
    }
