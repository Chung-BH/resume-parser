"""Semantic visual analysis from rendered DOCX pages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ollama_client import OllamaError, generate_json_with_images


class VisionAnalyzer:
    def __init__(self, model: str, ollama_url: str, enabled: bool = True) -> None:
        self.model = model
        self.ollama_url = ollama_url
        self.enabled = enabled

    def analyze(self, render: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        pngs = select_pages(render.get("pngs", []), max_pages=1)
        if render.get("mode") == "structural":
            return {
                **empty_result("render_required", "real DOCX rendering failed; structural preview is not suitable for vision analysis", pngs),
                "warnings": ["실제 Word/LibreOffice 렌더링이 실패해서 비전 분석을 건너뛰었습니다."],
            }
        if not self.enabled or not pngs:
            return empty_result("skipped", "vision skipped", pngs)

        vision_images = prepare_vision_images(pngs, suffix="vision_input")
        prompt = build_prompt(profile)
        try:
            payload = generate_json_with_images(
                prompt,
                vision_images,
                self.model,
                self.ollama_url,
                timeout=180,
                retries=0,
                max_side=640,
                num_predict=260,
                format_schema=vision_schema(),
            )
        except OllamaError as exc:
            return {
                **empty_result("failed", "vision failed", pngs),
                "warnings": [str(exc)],
            }
        if not isinstance(payload, dict):
            return {
                **empty_result("failed", "invalid vision JSON", pngs),
                "warnings": ["invalid vision JSON"],
            }
        return normalize_payload(payload, pngs)


def build_prompt(profile: dict[str, Any]) -> str:
    profile_keys = [key for key, value in profile.items() if value]
    return f"""
Return only valid minified JSON. No markdown. No explanation.

Look at this rendered Korean resume/application form image.
Find where each profile field should be written.
This is semantic layout understanding, not OCR only.

Profile keys:
{json.dumps(profile_keys, ensure_ascii=False)}

Return JSON with this exact meaning:
{{
  "status": "ok",
  "document_summary": "short",
  "field_targets": {{
    "name": "blank cell right of ??",
    "phone": "blank cell right of ???"
  }},
  "summary": "short"
}}

Rules:
- field_targets is an object, not an array.
- Values in field_targets must be short text, under 12 Korean words.
- Include only profile keys you can visually place.
- If you cannot see the form, return {{"status":"failed","document_summary":"failed","field_targets":{{}},"summary":"cannot see form"}}.
"""


def vision_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "document_summary": {"type": "string"},
            "field_targets": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
            "summary": {"type": "string"},
        },
        "required": ["status", "document_summary", "field_targets", "summary"],
    }

def normalize_payload(payload: dict[str, Any], source_images: list[str]) -> dict[str, Any]:
    field_candidates = list_of_dicts(payload.get("field_candidates"))
    if not field_candidates:
        field_candidates = list_of_dicts(payload.get("fields"))
    if not field_candidates and isinstance(payload.get("field_targets"), dict):
        field_candidates = [
            {
                "field": str(field),
                "page": 1,
                "label_seen": "",
                "target_area": str(target),
                "confidence": 0.7,
            }
            for field, target in payload["field_targets"].items()
            if target
        ]
    return {
        "status": str(payload.get("status") or "ok"),
        "document_summary": str(payload.get("document_summary") or payload.get("summary") or ""),
        "pages": list_of_dicts(payload.get("pages")),
        "tables": list_of_dicts(payload.get("tables")),
        "labels": list_of_dicts(payload.get("labels")),
        "blank_areas": list_of_dicts(payload.get("blank_areas")),
        "field_candidates": field_candidates,
        "fields": field_candidates,
        "warnings": list_of_strings(payload.get("warnings")),
        "summary": str(payload.get("summary") or payload.get("document_summary") or ""),
        "source_images": source_images,
    }


def empty_result(status: str, summary: str, source_images: list[str]) -> dict[str, Any]:
    return {
        "status": status,
        "document_summary": summary,
        "pages": [],
        "tables": [],
        "labels": [],
        "blank_areas": [],
        "field_candidates": [],
        "fields": [],
        "warnings": [],
        "summary": summary,
        "source_images": source_images,
    }


def list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def list_of_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def select_pages(pngs: list[str], max_pages: int) -> list[str]:
    existing = [str(path) for path in pngs if Path(path).exists()]
    existing.sort(key=page_sort_key)
    return existing[:max_pages]


def page_sort_key(path: str) -> tuple[int, int, str]:
    name = Path(path).stem.lower()
    digits = "".join(ch if ch.isdigit() else " " for ch in name).split()
    if digits:
        return (0, int(digits[-1]), path)
    try:
        size = -Path(path).stat().st_size
    except OSError:
        size = 0
    return (1, size, path)


def prepare_vision_images(image_paths: list[str], suffix: str) -> list[str]:
    prepared: list[str] = []
    for image_path in image_paths:
        path = Path(image_path)
        try:
            prepared.append(str(crop_content_image(path, suffix=suffix)))
        except Exception:
            prepared.append(str(path))
    return prepared


def crop_content_image(path: Path, suffix: str) -> Path:
    from PIL import Image, ImageChops

    image = Image.open(path).convert("RGB")
    background = Image.new("RGB", image.size, (255, 255, 255))
    diff = ImageChops.difference(image, background).convert("L")
    diff = diff.point(lambda value: 255 if value > 18 else 0)
    bbox = diff.getbbox()
    if not bbox:
        return path
    padding = 24
    left = max(0, bbox[0] - padding)
    top = max(0, bbox[1] - padding)
    right = min(image.width, bbox[2] + padding)
    bottom = min(image.height, bbox[3] + padding)
    cropped = image.crop((left, top, right, bottom))
    output = path.with_name(f"{path.stem}_{suffix}.jpg")
    cropped.save(output, format="JPEG", quality=82, optimize=True)
    return output
