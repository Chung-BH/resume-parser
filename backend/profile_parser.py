"""Profile parsing with qwen3."""

from __future__ import annotations

import json
import re
from typing import Any

from .ollama_client import OllamaError, generate_json
from .schemas import PROFILE_SCHEMA
from .utils import clean_text


class ProfileParser:
    def __init__(self, model: str, ollama_url: str, use_ai: bool = True) -> None:
        self.model = model
        self.ollama_url = ollama_url
        self.use_ai = use_ai

    def parse(self, text: str) -> dict[str, Any]:
        if self.use_ai:
            prompt = f"""
Return only valid JSON matching this schema:
{json.dumps(PROFILE_SCHEMA, ensure_ascii=False, indent=2)}

Rules:
- Extract only values present in the user's text.
- Preserve Korean.
- Use arrays for education, careers, certificates.
- Do not invent missing values.

USER_TEXT:
{text}
"""
            try:
                payload = generate_json(prompt, self.model, self.ollama_url, timeout=120)
                if isinstance(payload, dict):
                    return normalize_profile(payload)
            except OllamaError:
                pass
        return normalize_profile(fallback_parse(text))


def normalize_profile(payload: dict[str, Any]) -> dict[str, Any]:
    profile = json.loads(json.dumps(PROFILE_SCHEMA, ensure_ascii=False))
    for key in profile:
        if key in {"education", "careers", "certificates"}:
            value = payload.get(key, [])
            profile[key] = value if isinstance(value, list) else []
        elif key == "extra":
            value = payload.get(key, {})
            profile[key] = value if isinstance(value, dict) else {}
        else:
            profile[key] = clean_text(payload.get(key, ""))
    return profile


def fallback_parse(text: str) -> dict[str, Any]:
    profile = json.loads(json.dumps(PROFILE_SCHEMA, ensure_ascii=False))
    patterns = {
        "name": r"(?:이름|성명)\s*[:：]\s*(.+)",
        "english_name": r"(?:영문\s*이름|영문성명|영문)\s*[:：]\s*(.+)",
        "birth_date": r"(?:생년월일|생일)\s*[:：]\s*([0-9./-]+)",
        "gender": r"(?:성별)\s*[:：]\s*(.+)",
        "phone": r"(?:연락처|핸드폰|휴대폰|전화)\s*[:：]\s*([0-9 -]+)",
        "email": r"(?:이메일|e-mail|email)\s*[:：]\s*([^\s]+@[^\s]+)",
        "address": r"(?:주소)\s*[:：]\s*(.+)",
        "job": r"(?:지원직무|직무)\s*[:：]\s*(.+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            profile[key] = clean_text(match.group(1))
    return profile
