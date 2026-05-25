"""Model client router for Ollama and OpenAI-compatible GPT models."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from .ollama_client import (
    OllamaError,
    encode_image,
    extract_json,
    generate_json as generate_ollama_json,
    generate_json_with_images as generate_ollama_json_with_images,
    list_models,
)


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


def generate_json(
    prompt: str,
    model: str,
    ollama_url: str,
    timeout: int = 120,
    retries: int = 1,
    openai_api_key: str | None = None,
) -> Any:
    if not is_openai_model(model):
        return generate_ollama_json(prompt, model, ollama_url, timeout=timeout, retries=retries)
    return generate_openai_json(prompt, model, timeout=timeout, retries=retries, api_key=openai_api_key)


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
    openai_api_key: str | None = None,
) -> Any:
    if not is_openai_model(model):
        return generate_ollama_json_with_images(
            prompt,
            image_paths,
            model,
            ollama_url,
            timeout=timeout,
            retries=retries,
            max_side=max_side,
            num_predict=num_predict,
            format_schema=format_schema,
        )
    return generate_openai_json_with_images(
        prompt,
        image_paths,
        model,
        timeout=timeout,
        retries=retries,
        max_side=max_side,
        max_output_tokens=num_predict,
        format_schema=format_schema,
        api_key=openai_api_key,
    )


def is_openai_model(model: str) -> bool:
    value = model.strip().lower()
    return value.startswith(("gpt-", "o1", "o3", "o4", "o5", "chatgpt-"))


def require_openai_key(api_key: str | None = None) -> str:
    key = (api_key or os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        raise OllamaError("OpenAI API key is required. Set the OPENAI_API_KEY environment variable.")
    return key


def generate_openai_json(prompt: str, model: str, timeout: int = 120, retries: int = 1, api_key: str | None = None) -> Any:
    last_error: Exception | None = None
    current = prompt
    for _ in range(retries + 1):
        try:
            payload = post_openai_response(
                {
                    "model": model,
                    "input": current,
                    "text": {"format": {"type": "json_object"}},
                },
                timeout=timeout,
                api_key=api_key,
            )
            return extract_json(openai_response_text(payload))
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            current = prompt + "\n\nReturn one valid JSON object only. No markdown. No explanation."
    raise OllamaError(f"{model} JSON generation failed: {last_error}")


def generate_openai_json_with_images(
    prompt: str,
    image_paths: list[str | Path],
    model: str,
    timeout: int = 120,
    retries: int = 1,
    max_side: int = 720,
    max_output_tokens: int = 500,
    format_schema: dict[str, Any] | None = None,
    api_key: str | None = None,
) -> Any:
    last_error: Exception | None = None
    content = [{"type": "input_text", "text": prompt}]
    for path in image_paths:
        image = encode_image(path, max_side=max_side)
        content.append({"type": "input_image", "image_url": f"data:image/jpeg;base64,{image}"})
    current_content = content
    for _ in range(retries + 1):
        try:
            payload = post_openai_response(
                {
                    "model": model,
                    "input": [{"role": "user", "content": current_content}],
                    "max_output_tokens": max_output_tokens,
                    "text": {"format": openai_response_format(format_schema, "vision_analysis")},
                },
                timeout=timeout,
                api_key=api_key,
            )
            return extract_json(openai_response_text(payload))
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            current_content = [{"type": "input_text", "text": prompt + "\n\nReturn one valid JSON object only. No markdown. No explanation."}]
            current_content.extend(content[1:])
    raise OllamaError(f"{model} vision JSON generation failed: {last_error}")


def openai_response_format(format_schema: dict[str, Any] | None, name: str) -> dict[str, Any]:
    if not format_schema:
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "name": name[:64],
        "strict": True,
        "schema": make_strict_json_schema(format_schema),
    }


def make_strict_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    normalized = json.loads(json.dumps(schema))

    def visit(node: Any) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "object":
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["required"] = list(properties.keys())
                for child in properties.values():
                    visit(child)
            node["additionalProperties"] = False
        elif node.get("type") == "array":
            visit(node.get("items"))
        for keyword in ("anyOf", "oneOf"):
            if isinstance(node.get(keyword), list):
                for child in node[keyword]:
                    visit(child)

    visit(normalized)
    return normalized


def post_openai_response(payload: dict[str, Any], timeout: int, api_key: str | None) -> dict[str, Any]:
    request = Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {require_openai_key(api_key)}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def openai_response_text(payload: dict[str, Any]) -> str:
    output_text = str(payload.get("output_text") or "").strip()
    if output_text:
        return output_text
    chunks: list[str] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and content.get("type") in {"output_text", "text"}:
                chunks.append(str(content.get("text") or ""))
    return "\n".join(chunk for chunk in chunks if chunk).strip()
