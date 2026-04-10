import json
import re

import httpx

from app.core.config import settings


OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
GEMINI_GENERATE_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

VALID_INTENTS = {
    "interested": "Interested",
    "not interested": "Not Interested",
    "follow-up needed": "Follow-up Needed",
    "follow up needed": "Follow-up Needed",
    "inquiry": "Inquiry",
    "already enrolled": "Already Enrolled",
    "spam": "Spam",
    "ignore": "IGNORE",
}

DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
TELUGU_RE = re.compile(r"[\u0C00-\u0C7F]")


def _normalize_intent(value: str) -> str | None:
    normalized = " ".join((value or "").strip().lower().split())
    return VALID_INTENTS.get(normalized)


def _is_likely_english(text: str) -> bool:
    normalized = " ".join((text or "").split())
    if not normalized:
        return False
    if DEVANAGARI_RE.search(normalized) or TELUGU_RE.search(normalized):
        return False

    letters = [ch for ch in normalized if ch.isalpha()]
    if not letters:
        return False

    ascii_letters = [ch for ch in letters if ch.isascii()]
    return (len(ascii_letters) / len(letters)) >= 0.85


def _clean_summary(value: str) -> str:
    cleaned = " ".join((value or "").replace("\n", " ").split())
    if len(cleaned) > 320:
        cleaned = cleaned[:320].rstrip()
    return cleaned


def _parse_classifier_output(raw_output: str) -> tuple[str | None, str | None]:
    raw = (raw_output or "").strip()
    if not raw:
        return None, None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, dict):
        intent = _normalize_intent(str(parsed.get("INTENT") or parsed.get("intent") or ""))
        summary = str(parsed.get("SUMMARY") or parsed.get("summary") or "").strip()
        return intent, summary or None

    intent_match = re.search(r"^\s*INTENT\s*:\s*(.+)$", raw, flags=re.IGNORECASE | re.MULTILINE)
    summary_match = re.search(r"^\s*SUMMARY\s*:\s*(.+)$", raw, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)

    intent_value = _normalize_intent(intent_match.group(1)) if intent_match else None
    summary_value = summary_match.group(1).strip() if summary_match else None
    if summary_value:
        summary_value = summary_value.splitlines()[0].strip()
    return intent_value, summary_value


def _build_classifier_prompt(text: str) -> str:
    return f"""
You are given an audio call transcription of a school admission coordinator speaking with a parent or student.

Tasks:
1. Understand the conversation. The transcript may represent English, Hindi, or Telugu speech.
2. Identify the intent of the conversation.
3. Generate a clear and concise summary in English.

Return output in EXACT format:
INTENT: <Interested / Not Interested / Follow-up Needed / Inquiry / Already Enrolled / Spam / IGNORE>
SUMMARY: <Short English summary OR IGNORE>

Rules:
- Do NOT mention language in output
- Summary must always be in English
- Keep summary concise (2-4 lines max)
- Choose the most appropriate intent:
  - Interested -> shows clear interest in admission
  - Not Interested -> declines or not willing
  - Follow-up Needed -> needs callback or more info later
  - Inquiry -> asking general questions
  - Already Enrolled -> completed admission
  - Spam -> irrelevant or wrong call
- If transcript has no meaningful content, return exactly:
  INTENT: IGNORE
  SUMMARY: IGNORE

Transcript:
{text[:12000]}
""".strip()


def _classify_with_openai(prompt: str) -> str:
    if not settings.openai_api_key:
        return ""

    body = {
        "model": settings.openai_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=max(20, settings.gemini_timeout_seconds)) as client:
        response = client.post(OPENAI_CHAT_URL, json=body, headers=headers)
        response.raise_for_status()
        payload = response.json()

    return str(payload["choices"][0]["message"]["content"] or "").strip()


def _classify_with_gemini(prompt: str) -> str:
    if not settings.gemini_api_key:
        return ""

    url = GEMINI_GENERATE_URL_TEMPLATE.format(model=settings.gemini_model)
    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
        },
    }

    with httpx.Client(timeout=max(20, settings.gemini_timeout_seconds)) as client:
        response = client.post(url, params={"key": settings.gemini_api_key}, json=body)
        response.raise_for_status()
        payload = response.json()

    candidates = payload.get("candidates") or []
    if not candidates:
        return ""

    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    text_parts = [str(part.get("text") or "").strip() for part in parts if str(part.get("text") or "").strip()]
    return "\n".join(text_parts).strip()


def classify_intent_summary(text: str, fallback_summary: str = "") -> tuple[str, str]:
    normalized_text = " ".join((text or "").split())
    if len(normalized_text) < 15:
        return "IGNORE", "IGNORE"

    prompt = _build_classifier_prompt(normalized_text)

    raw_output = ""
    if settings.gemini_enabled and settings.gemini_api_key:
        raw_output = _classify_with_gemini(prompt)

    if not raw_output:
        raw_output = _classify_with_openai(prompt)

    intent, summary = _parse_classifier_output(raw_output)
    if not intent:
        intent = "Inquiry"

    if intent == "IGNORE":
        return "IGNORE", "IGNORE"

    cleaned_summary = _clean_summary(summary or fallback_summary)
    if not cleaned_summary:
        cleaned_summary = "Caller discussed school admission details and requested additional guidance."

    if not _is_likely_english(cleaned_summary):
        fallback_clean = _clean_summary(fallback_summary)
        if fallback_clean and _is_likely_english(fallback_clean):
            cleaned_summary = fallback_clean
        else:
            return "IGNORE", "IGNORE"

    return intent, cleaned_summary
