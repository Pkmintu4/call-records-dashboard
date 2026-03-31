from urllib.parse import urlencode

import httpx

from app.core.config import settings


TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


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


def get_google_access_token() -> str:
    client_id = settings.google_client_id.strip()
    client_secret = settings.google_client_secret.strip()
    refresh_token = settings.google_refresh_token.strip()

    if not client_id or not client_secret or not refresh_token:
        raise ValueError("Missing Google OAuth credentials in environment")

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
        "scope": "https://www.googleapis.com/auth/drive.readonly",
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
