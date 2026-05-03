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
The transcript is speaker-diarized: each speaker turn is labeled as "Speaker 1:", "Speaker 2:", etc.
Identify which speaker is the Parent and which is the School Staff based on the conversation context.
The transcript language is always one of these only: English, Telugu, or mix of telugu and english.
Do NOT assume or use any other language.
Write outputs in simple English only.

IMPORTANT: Analyze the COMPLETE conversation from ALL speakers. Do not ignore any part of the transcript.

For this transcript, extract these KPIs.

Speaker Identification:
- speaker_1_role (parent / staff / unknown)
- speaker_2_role (parent / staff / unknown)
- speaker_talk_balance (e.g. "Speaker 1 dominated" / "balanced" / "Speaker 2 dominated")

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

Give an overall summary of the full conversation in simple, clear English.
   Keep it short and clear: 1–2 paragraphs explaining the main points clearly.
   Reference what each speaker said.


Return STRICT JSON only with exactly these keys:
summary, sentiment, intent_score, visit_intent, parent_concerns,
competitor_schools_mentioned, lead_source, key_questions_asked, friction_points,
admission_probability, persuasion_score, response_clarity, politeness_score,
missed_conversion_opportunity, speaker_1_role, speaker_2_role, speaker_talk_balance

Transcript:
{text[:16000]}
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
        "speaker_1_role": str(parsed.get("speaker_1_role", "unknown")).strip().lower() or "unknown",
        "speaker_2_role": str(parsed.get("speaker_2_role", "unknown")).strip().lower() or "unknown",
        "speaker_talk_balance": str(parsed.get("speaker_talk_balance", "balanced")).strip() or "balanced",
    }

    if kpis["visit_intent"] not in {"yes", "no", "maybe"}:
        kpis["visit_intent"] = "maybe"
    if kpis["missed_conversion_opportunity"] not in {"yes", "no"}:
        kpis["missed_conversion_opportunity"] = "no"

    return score, label, summary, kpis
