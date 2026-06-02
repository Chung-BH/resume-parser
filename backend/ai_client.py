"""Ollama model client wrapper."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .ollama_client import (
    OllamaError,
    generate_json as generate_ollama_json,
    generate_json_with_images as generate_ollama_json_with_images,
    list_models,
)


def generate_json(
    prompt: str,
    model: str,
    ollama_url: str,
    timeout: int = 120,
    retries: int = 1,
) -> Any:
    return generate_ollama_json(prompt, model, ollama_url, timeout=timeout, retries=retries)


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
