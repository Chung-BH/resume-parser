"""Ollama API client."""

from __future__ import annotations

import base64
from io import BytesIO
import json
import re
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


REPAIR_TEXT_LIMIT = 12000


class OllamaError(RuntimeError):
    """Raised when Ollama cannot return usable JSON."""


def generate_json(prompt: str, model: str, ollama_url: str, timeout: int = 120, retries: int = 1) -> Any:
    last_error: Exception | None = None
    current = prompt
    for _ in range(retries + 1):
        try:
            payload = post_json(
                f"{ollama_url.rstrip('/')}/api/generate",
                {
                    "model": model,
                    "prompt": current,
                    "stream": False,
                    "format": "json",
                    "think": False,
                    "options": {"temperature": 0},
                },
                timeout,
            )
            text = response_text(payload)
            try:
                return extract_json(text)
            except json.JSONDecodeError:
                return repair_json(text, model, ollama_url, timeout)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            current = prompt + "\n\nReturn one valid JSON object only. No markdown. No explanation."
    raise OllamaError(f"{model} JSON generation failed: {last_error}")


def generate_json_with_images(
    prompt: str,
    image_paths: list[str | Path],
    model: str,
    ollama_url: str,
    timeout: int = 120,
    retries: int = 1,
    max_side: int = 720,
    num_predict: int = 500,
    format_schema: dict[str, Any] | None = None,
) -> Any:
    images = [encode_image(path, max_side=max_side) for path in image_paths]
    last_error: Exception | None = None
    current = prompt
    for _ in range(retries + 1):
        try:
            request_payload = {
                "model": model,
                "prompt": current,
                "images": images,
                "stream": False,
                "format": format_schema or "json",
                "think": False,
                "options": {"temperature": 0, "num_predict": num_predict},
            }
            payload = post_json(
                f"{ollama_url.rstrip('/')}/api/generate",
                request_payload,
                timeout,
            )
            text = response_text(payload)
            try:
                return extract_json(text)
            except json.JSONDecodeError:
                return repair_json(text, model, ollama_url, timeout)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            current = prompt + "\n\nReturn one valid JSON object only. No markdown. No explanation."
    raise OllamaError(f"{model} vision JSON generation failed: {last_error}")


def encode_image(path: str | Path, max_side: int = 900) -> str:
    source = Path(path)
    try:
        from PIL import Image

        image = Image.open(source).convert("RGB")
        width, height = image.size
        scale = min(1.0, max_side / max(width, height))
        if scale < 1.0:
            image = image.resize((int(width * scale), int(height * scale)))
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=82, optimize=True)
        return base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception:
        return base64.b64encode(source.read_bytes()).decode("ascii")


def list_models(ollama_url: str = "http://localhost:11434", timeout: int = 5) -> list[str]:
    try:
        request = Request(f"{ollama_url.rstrip('/')}/api/tags", method="GET")
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []
    return [str(item["name"]) for item in payload.get("models", []) if isinstance(item, dict) and item.get("name")]


def extract_json(text: str) -> Any:
    text = strip_thinking(text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1).strip())
    starts = [index for index in (text.find("{"), text.find("[")) if index >= 0]
    if not starts:
        raise json.JSONDecodeError("no JSON opener", text, 0)
    start = min(starts)
    closer = "}" if text[start] == "{" else "]"
    end = text.rfind(closer)
    if end < start:
        raise json.JSONDecodeError("no JSON closer", text, start)
    return json.loads(text[start : end + 1])


def repair_json(text: str, model: str, ollama_url: str, timeout: int) -> Any:
    broken = strip_thinking(text).strip()
    if len(broken) > REPAIR_TEXT_LIMIT:
        broken = broken[: REPAIR_TEXT_LIMIT // 2] + "\n...\n" + broken[-REPAIR_TEXT_LIMIT // 2 :]
    prompt = f"""
Return only one valid JSON object or array. No markdown. No explanation.

Fix the JSON syntax in the broken model output below.
Do not add new fields.
Do not remove meaningful values.
Preserve Korean text exactly when possible.

BROKEN_OUTPUT:
{broken}
"""
    payload = post_json(
        f"{ollama_url.rstrip('/')}/api/generate",
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "think": False,
            "options": {"temperature": 0},
        },
        timeout,
    )
    return extract_json(response_text(payload))


def strip_thinking(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL)
    return text.strip()


def response_text(payload: dict[str, Any]) -> str:
    response = str(payload.get("response") or "").strip()
    if response:
        return response
    return str(payload.get("thinking") or "").strip()


def post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))
