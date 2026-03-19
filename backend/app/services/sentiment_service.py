import json
import re

import httpx

from app.core.config import settings


OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"


def _coerce_sentiment(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"positive", "negative", "neutral"}:
        return normalized
    return "neutral"


def _score_from_sentiment(sentiment: str) -> float:
    if sentiment == "positive":
        return 0.8
    if sentiment == "negative":
        return -0.8
    return 0.0


def _normalize_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _to_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def analyze_sentiment(text: str) -> tuple[float, str, str, dict[str, object]]:
    if not settings.openai_api_key:
        raise ValueError("Missing OPENAI_API_KEY in environment")

    prompt = f"""
You are analyzing a phone call between a Parent and a School Admission Coordinator.
The transcript may contain Telugu, Hindi, and English mixed. Understand all languages.
Write outputs in simple English only.

For this transcript, extract these KPIs.

Parent KPIs:
- sentiment (positive / neutral / negative)
- intent_score (1-5)
- visit_intent (yes / no / maybe)
- parent_concerns (fees, transport, curriculum, safety, etc)
- competitor_schools_mentioned
- lead_source (google, referral, doctor, friend, unknown)

Conversation KPIs:
- key_questions_asked
- friction_points
- admission_probability (0-100)

Staff KPIs:
- persuasion_score (1-5)
- response_clarity (1-5)
- politeness_score (1-5)
- missed_conversion_opportunity (yes/no)

Also provide a short summary in very simple English (3-6 short sentences, one paragraph).

Return STRICT JSON only with exactly these keys:
summary, sentiment, intent_score, visit_intent, parent_concerns,
competitor_schools_mentioned, lead_source, key_questions_asked, friction_points,
admission_probability, persuasion_score, response_clarity, politeness_score,
missed_conversion_opportunity

Transcript:
{text[:12000]}
""".strip()

    body = {
        "model": settings.openai_model,
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
    }

    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=60) as client:
        response = client.post(OPENAI_CHAT_URL, json=body, headers=headers)
        response.raise_for_status()
        payload = response.json()

    content = payload["choices"][0]["message"]["content"] or "{}"

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = {}

    summary = str(parsed.get("summary") or "No summary available").strip()
    label = _coerce_sentiment(str(parsed.get("sentiment") or "neutral"))
    score = _score_from_sentiment(label)

    kpis: dict[str, object] = {
        "summary": summary,
        "sentiment": label,
        "intent_score": max(1, min(5, _to_int(parsed.get("intent_score"), 3))),
        "visit_intent": str(parsed.get("visit_intent", "maybe")).strip().lower() if str(parsed.get("visit_intent", "")).strip() else "maybe",
        "parent_concerns": _normalize_list(parsed.get("parent_concerns")),
        "competitor_schools_mentioned": _normalize_list(parsed.get("competitor_schools_mentioned")),
        "lead_source": str(parsed.get("lead_source", "unknown")).strip().lower() or "unknown",
        "key_questions_asked": _normalize_list(parsed.get("key_questions_asked")),
        "friction_points": _normalize_list(parsed.get("friction_points")),
        "admission_probability": max(0, min(100, _to_int(parsed.get("admission_probability"), 50))),
        "persuasion_score": max(1, min(5, _to_int(parsed.get("persuasion_score"), 3))),
        "response_clarity": max(1, min(5, _to_int(parsed.get("response_clarity"), 3))),
        "politeness_score": max(1, min(5, _to_int(parsed.get("politeness_score"), 3))),
        "missed_conversion_opportunity": str(parsed.get("missed_conversion_opportunity", "no")).strip().lower() or "no",
    }

    if kpis["visit_intent"] not in {"yes", "no", "maybe"}:
        kpis["visit_intent"] = "maybe"
    if kpis["missed_conversion_opportunity"] not in {"yes", "no"}:
        kpis["missed_conversion_opportunity"] = "no"

    return score, label, summary, kpis
