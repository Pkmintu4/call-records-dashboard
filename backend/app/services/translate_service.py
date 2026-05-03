import logging

import httpx

from app.core.config import settings


logger = logging.getLogger(__name__)

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"

def translate_to_english(text: str) -> str:
    """
    Translates the given transcript text to English using OpenAI.
    If the text is already in English, it will just return it cleaned up.
    """
    normalized_text = (text or "").strip()
    if not normalized_text:
        return ""

    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY is not set. Skipping translation.")
        return normalized_text

    prompt = f"""
You are an expert translator. Your task is to translate the following call transcript into clear and natural English.
- If the text is in Telugu, Hindi, or a mix of languages, translate it entirely to English.
- If the text is already in English, ensure it is grammatically clean and return it.
- Preserve any speaker labels (like "Speaker 1:", "Parent:", etc.) exactly as they appear.
- Do NOT add any extra commentary, notes, or introductory text. Return ONLY the translated transcript.

Transcript:
{normalized_text}
""".strip()

    body = {
        "model": settings.openai_model,
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }

    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=120) as client:
            response = client.post(OPENAI_CHAT_URL, json=body, headers=headers)
            response.raise_for_status()
            payload = response.json()
            
        translated_content = payload["choices"][0]["message"]["content"]
        if translated_content:
            return translated_content.strip()
    except Exception as e:
        logger.exception("Failed to translate transcript: %s", e)
        # Fallback to the original text if translation fails
        return normalized_text
        
    return normalized_text
