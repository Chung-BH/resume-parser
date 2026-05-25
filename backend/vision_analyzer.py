"""Semantic visual analysis from rendered DOCX pages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ai_client import OllamaError, generate_json_with_images


class VisionAnalyzer:
    def __init__(self, model: str, ollama_url: str, enabled: bool = True, openai_api_key: str | None = None) -> None:
        self.model = model
        self.ollama_url = ollama_url
        self.enabled = enabled
        self.openai_api_key = openai_api_key

    def analyze(self, render: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        pngs = select_pages(render.get("pngs", []), max_pages=3)
        if render.get("mode") == "structural":
            return {
                **empty_result("render_required", "real DOCX rendering failed; structural preview is not suitable for vision analysis", pngs),
                "warnings": ["실제 Word/LibreOffice 렌더링이 실패해서 비전 분석을 건너뛰었습니다."],
            }
        if not self.enabled or not pngs:
            return empty_result("skipped", "vision skipped", pngs)

        merged = empty_result("ok", "", [])
        summaries: list[str] = []
        warnings: list[str] = []
        for page_number, png in enumerate(pngs, start=1):
            vision_inputs = prepare_vision_inputs(png, page_number=page_number)
            vision_images = [item["path"] for item in vision_inputs]
            merged["source_images"].extend(vision_images)
            prompt = build_prompt(profile, vision_inputs)
            try:
                payload = generate_json_with_images(
                    prompt,
                    vision_images,
                    self.model,
                    self.ollama_url,
                    timeout=240,
                    retries=0,
                    max_side=1100,
                    num_predict=1400,
                    format_schema=vision_schema(),
                    openai_api_key=self.openai_api_key,
                )
            except OllamaError as exc:
                warnings.append(f"page {page_number}: {exc}")
                continue
            if not isinstance(payload, dict):
                warnings.append(f"page {page_number}: invalid vision JSON")
                continue
            page_result = normalize_payload(payload, vision_images, page_number=page_number)
            merged["visual_fields"].extend(page_result["visual_fields"])
            merged["field_candidates"].extend(page_result["field_candidates"])
            merged["fields"].extend(page_result["fields"])
            if page_result.get("summary"):
                summaries.append(str(page_result["summary"]))

        merged["warnings"] = warnings
        merged["summary"] = " / ".join(summaries)
        merged["document_summary"] = merged["summary"]
        if not merged["visual_fields"]:
            merged["status"] = "failed"
            merged["summary"] = "vision failed"
            merged["document_summary"] = "vision failed"
        return merged


def build_prompt(profile: dict[str, Any], vision_inputs: list[dict[str, str]]) -> str:
    profile_keys = [key for key, value in profile.items() if value]
    example_crop = vision_inputs[1]["crop_id"] if len(vision_inputs) > 1 else vision_inputs[0]["crop_id"]
    image_order = [
        {
            "image_index": index + 1,
            "crop_id": item["crop_id"],
            "description": item["description"],
        }
        for index, item in enumerate(vision_inputs)
    ]
    return f"""
Return only valid minified JSON. No markdown. No explanation.

Look at this rendered Korean resume/application form image.
Observe the visible form structure. Do not guess DOCX table/row/cell numbers.
Your job is visual observation: labels, blank input areas, nearby text, and position.

Profile keys:
{json.dumps(profile_keys, ensure_ascii=False)}

Priority:
- Return one visual_field for each clearly visible profile key when possible.
- Prioritize personal information fields first: name, english_name, birth_date, gender, phone, email, address, job.
- Then include repeated sections: education, careers, certificates, languages, military.
- For repeated sections, use the section heading or row area, not each column header as a separate field.

Images are provided in this exact order:
{json.dumps(image_order, ensure_ascii=False)}

Return JSON with this exact shape:
{{
  "status": "ok",
  "document_summary": "short",
  "visual_fields": [
    {{
      "field": "name",
      "label_seen": "성명",
      "target_area": "blank cell right of the label",
      "crop_id": "{example_crop}",
      "relative_position": "top-left applicant information table",
      "nearby_text": ["성명", "영문", "생년월일"],
      "confidence": 0.84
    }}
  ],
  "summary": "short"
}}

Rules:
- visual_fields is an array.
- Return at most 10 visual_fields.
- field must be one of the profile keys when the match is clear. Use "" when only the label is visible but the profile key is uncertain.
- label_seen must be the exact visible Korean/English label when readable.
- target_area must describe the blank area to write into, not the label cell.
- crop_id must be one of the provided crop_id values.
- nearby_text should include 1 to 5 visible neighboring labels or headings.
- Include only fields or labels related to the provided profile keys.
- Do not include unrelated sections such as training, awards, or hobbies unless the profile keys include them.
- Include the foreign language section when the profile keys include languages.
- Include the military service section when the profile keys include military.
- For repeated sections such as education, careers, and certificates, return one visual field per section, not one per row.
- If you cannot see the form, return {{"status":"failed","document_summary":"failed","visual_fields":[],"summary":"cannot see form"}}.
"""


def vision_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "document_summary": {"type": "string"},
            "visual_fields": {
                "type": "array",
                "maxItems": 10,
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string"},
                        "label_seen": {"type": "string"},
                        "target_area": {"type": "string"},
                        "crop_id": {"type": "string"},
                        "relative_position": {"type": "string"},
                        "nearby_text": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "confidence": {"type": "number"},
                    },
                    "required": [
                        "field",
                        "label_seen",
                        "target_area",
                        "crop_id",
                        "relative_position",
                        "nearby_text",
                        "confidence",
                    ],
                },
            },
            "summary": {"type": "string"},
        },
        "required": ["status", "document_summary", "visual_fields", "summary"],
    }

def normalize_payload(payload: dict[str, Any], source_images: list[str], page_number: int = 1) -> dict[str, Any]:
    visual_fields = normalize_visual_fields(payload.get("visual_fields"), page_number=page_number)
    field_candidates = visual_fields or list_of_dicts(payload.get("field_candidates"))
    if not field_candidates:
        field_candidates = list_of_dicts(payload.get("fields"))
    if not field_candidates and isinstance(payload.get("field_targets"), dict):
        field_candidates = [
            {
                "field": str(field),
                "page": page_number,
                "label_seen": "",
                "target_area": str(target),
                "crop_id": "page1_full",
                "relative_position": "",
                "nearby_text": [],
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
        "visual_fields": field_candidates,
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
        "visual_fields": [],
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


def normalize_visual_fields(value: Any, page_number: int = 1) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    fields: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        label_seen = str(item.get("label_seen") or "").strip()
        target_area = str(item.get("target_area") or "").strip()
        if not label_seen and not target_area:
            continue
        fields.append(
            {
                "field": str(item.get("field") or "").strip(),
                "page": page_number,
                "label_seen": label_seen,
                "target_area": target_area,
                "crop_id": str(item.get("crop_id") or "").strip(),
                "relative_position": str(item.get("relative_position") or "").strip(),
                "nearby_text": list_of_strings(item.get("nearby_text"))[:5],
                "confidence": clamp_float(item.get("confidence"), 0.5),
            }
        )
    return fields[:40]


def clamp_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


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


def prepare_vision_inputs(image_path: str, page_number: int = 1) -> list[dict[str, str]]:
    path = Path(image_path)
    try:
        content = crop_content_image(path, suffix="vision_full")
        crops = split_vertical_crops(content, suffix="vision", page_number=page_number)
        return [
            {
                "crop_id": f"page{page_number}_full",
                "description": f"page {page_number} full visible content area",
                "path": str(content),
            },
            *crops,
        ]
    except Exception:
        return [{"crop_id": f"page{page_number}_full", "description": f"page {page_number} full page image", "path": str(path)}]


def split_vertical_crops(path: Path, suffix: str, page_number: int = 1) -> list[dict[str, str]]:
    from PIL import Image

    image = Image.open(path).convert("RGB")
    bands = [
        (f"page{page_number}_top", f"page {page_number} top third"),
        (f"page{page_number}_middle", f"page {page_number} middle third"),
        (f"page{page_number}_bottom", f"page {page_number} bottom third"),
    ]
    crops: list[dict[str, str]] = []
    for index, (crop_id, description) in enumerate(bands):
        top = image.height * index // len(bands)
        bottom = image.height * (index + 1) // len(bands)
        padding = max(20, image.height // 40)
        top = max(0, top - padding)
        bottom = min(image.height, bottom + padding)
        crop = image.crop((0, top, image.width, bottom))
        output = path.with_name(f"{path.stem}_{suffix}_{crop_id}.jpg")
        crop.save(output, format="JPEG", quality=84, optimize=True)
        crops.append({"crop_id": crop_id, "description": description, "path": str(output)})
    return crops


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
