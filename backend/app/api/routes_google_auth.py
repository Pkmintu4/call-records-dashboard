import secrets

from fastapi import APIRouter, HTTPException, Query

from app.integrations.google_oauth import build_google_auth_url, exchange_code_for_tokens, is_service_account_mode


router = APIRouter()


@router.get("/auth-url")
def get_google_auth_url() -> dict[str, str | bool]:
    try:
        if is_service_account_mode():
            return {
                "auth_mode": "service_account",
                "requires_user_auth": False,
                "message": "Service-account credentials detected. OAuth refresh-token flow is not required.",
                "auth_url": "",
            }

        state = secrets.token_urlsafe(16)
        url = build_google_auth_url(state)
        return {
            "auth_mode": "oauth",
            "requires_user_auth": True,
            "auth_url": url,
            "state": state,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/callback")
def google_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str | None = Query(default=None),
) -> dict[str, str]:
    try:
        tokens = exchange_code_for_tokens(code)
        response = {
            "message": "Copy refresh_token into GOOGLE_REFRESH_TOKEN in your .env file (OAuth mode only)",
            "refresh_token": tokens.get("refresh_token", ""),
            "token_type": tokens.get("token_type", "Bearer"),
        }
        if state:
            response["state"] = state
        return response
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
