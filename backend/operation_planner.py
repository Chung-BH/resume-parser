"""Operation plan generation.

LLMs only generate JSON plans. Python validates and applies them.
"""

from __future__ import annotations

import json
from typing import Any

from .ollama_client import OllamaError, generate_json
from .utils import clean_text


class OperationPlanner:
    def __init__(self, model: str, ollama_url: str, enabled: bool = True) -> None:
        self.model = model
        self.ollama_url = ollama_url
        self.enabled = enabled

    def plan(self, profile: dict[str, Any], layout: dict[str, Any], vision: dict[str, Any]) -> dict[str, Any]:
        fields = profile_to_fields(profile)
        if not fields:
            return {"operations": [], "summary": "No profile values to write.", "status": "empty_profile"}
        if not self.enabled:
            return {"operations": [], "summary": "AI planner disabled. No fallback writes are generated.", "status": "disabled"}
        operations: list[dict[str, Any]] = []
        errors: list[str] = []
        if vision.get("status") != "ok":
            errors.extend(str(item) for item in vision.get("warnings", []))
            errors.append("Vision analysis unavailable; qwen3 planner used DOCX layout JSON only.")
        used_targets: set[str] = set()
        for field in fields:
            try:
                payload = generate_json(
                    build_prompt(field, layout, vision, used_targets),
                    self.model,
                    self.ollama_url,
                    timeout=45,
                )
            except OllamaError as exc:
                errors.append(f"{field['field']}: {exc}")
                continue
            op = normalize_operation(payload, field, layout, used_targets)
            if op:
                used_targets.add(locator_from_target(op["target"]))
                operations.append(op)
        return {
            "operations": operations,
            "summary": f"Generated {len(operations)} operations from {len(fields)} profile fields.",
            "status": "planned" if operations else "no_operations",
            "errors": errors,
        }


def build_prompt(field: dict[str, str], layout: dict[str, Any], vision: dict[str, Any], used_targets: set[str]) -> str:
    candidates = [
        item
        for item in layout.get("input_candidates", [])[:280]
        if isinstance(item, dict) and item.get("locator") not in used_targets
    ]
    compact_layout = {
        "summary": layout.get("summary", {}),
        "labels": layout.get("labels", [])[:120],
        "input_candidates": candidates,
    }
    compact_vision = {
        "status": vision.get("status"),
        "document_summary": vision.get("document_summary"),
        "summary": vision.get("summary"),
        "pages": vision.get("pages", [])[:10],
        "tables": vision.get("tables", [])[:80],
        "labels": vision.get("labels", [])[:120],
        "blank_areas": vision.get("blank_areas", [])[:120],
        "field_candidates": relevant_vision_candidates(vision, field["field"]),
        "warnings": vision.get("warnings", [])[:30],
    }
    return f"""
Return only valid JSON.

You generate ONE DOCX operation for a local document agent.
You do not edit files. Python will apply your JSON operation.

Hard constraints:
- Choose at most one existing DOCX input candidate.
- target must correspond to one locator from DOCX_LAYOUT.input_candidates.
- Do not choose label cells.
- Do not invent cells, rows, tables, placeholders, or coordinates.
- If uncertain, return {{"operation": null, "summary": "reason"}}.

How to use VISION:
- VISION is semantic visual evidence from rendered page images.
- Prefer targets whose DOCX neighbor labels match VISION.field_candidates.target_area.
- If VISION says an area is a label/header/cramped area, avoid it.
- If VISION is failed/skipped/unavailable, use DOCX_LAYOUT labels and input_candidates.
- If DOCX_LAYOUT and successful VISION conflict, choose no operation instead of guessing.
- Your reason must mention both DOCX evidence and visual semantic evidence.

Operation format:
{{
  "operation": {{
    "op": "set_cell_text",
    "field": "{field['field']}",
    "value": {json.dumps(field['value'], ensure_ascii=False)},
    "target": {{"table": 0, "row": 1, "cell": 6}},
    "confidence": 0.8,
    "reason": "specific evidence"
  }},
  "summary": "short summary"
}}

FIELD:
{json.dumps(field, ensure_ascii=False, indent=2)}

FIELD_INTENT:
{json.dumps(field_intent(field["field"]), ensure_ascii=False)}

DOCX_LAYOUT:
{json.dumps(compact_layout, ensure_ascii=False, indent=2)}

VISION:
{json.dumps(compact_vision, ensure_ascii=False, indent=2)}
"""


def relevant_vision_candidates(vision: dict[str, Any], field: str) -> list[dict[str, Any]]:
    base = field.split("[", 1)[0]
    candidates = vision.get("field_candidates") or vision.get("fields") or []
    if not isinstance(candidates, list):
        return []
    relevant: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        item_field = str(item.get("field") or "")
        if item_field == field or item_field == base or item_field.startswith(base):
            relevant.append(item)
    if relevant:
        return relevant[:20]
    return [item for item in candidates[:20] if isinstance(item, dict)]


def profile_to_fields(profile: dict[str, Any]) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    for key in ["name", "english_name", "birth_date", "gender", "phone", "email", "address", "job"]:
        value = clean_text(profile.get(key))
        if value:
            fields.append({"field": key, "value": value})
    for index, row in enumerate(profile.get("education", []) or []):
        value = row_to_value(row, ["period", "school", "major"])
        if value:
            fields.append({"field": f"education[{index}]", "value": value})
    for index, row in enumerate(profile.get("careers", []) or []):
        value = row_to_value(row, ["period", "company", "position", "role"])
        if value:
            fields.append({"field": f"careers[{index}]", "value": value})
    for index, row in enumerate(profile.get("certificates", []) or []):
        value = row_to_value(row, ["name", "issuer", "date"])
        if value:
            fields.append({"field": f"certificates[{index}]", "value": value})
    return fields


def row_to_value(row: Any, keys: list[str]) -> str:
    if isinstance(row, str):
        return clean_text(row)
    if isinstance(row, dict):
        return " / ".join(clean_text(row.get(key)) for key in keys if clean_text(row.get(key)))
    return ""


def field_intent(field: str) -> str:
    base = field.split("[", 1)[0]
    intents = {
        "name": "Korean applicant name; likely near labels 성명 or 이름.",
        "english_name": "English name; likely near labels 영문 or 영문성명.",
        "birth_date": "Birth date; likely near label 생년월일.",
        "gender": "Gender; likely near label 성별.",
        "phone": "Phone/mobile number; likely near labels 연락처, 핸드폰, 휴대폰, 전화.",
        "email": "Email address; likely near labels 이메일, e-mail, email.",
        "address": "Home address; likely near label 주소.",
        "job": "Desired job/position; likely near labels 지원직무 or 직무.",
        "education": "Education entry; likely in 학력 section.",
        "careers": "Career entry; likely in 경력 section.",
        "certificates": "Certificate/license entry; likely in 자격증 section.",
    }
    return intents.get(base, field)


def normalize_operation(payload: Any, field: dict[str, str], layout: dict[str, Any], used_targets: set[str]) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    operation = payload.get("operation")
    if not isinstance(operation, dict):
        return None
    if operation.get("op") != "set_cell_text" or operation.get("field") != field["field"]:
        return None
    target = operation.get("target")
    if not isinstance(target, dict):
        return None
    try:
        locator = locator_from_target(target)
    except (TypeError, ValueError):
        return None
    valid = {item["locator"] for item in layout.get("input_candidates", []) if isinstance(item, dict)}
    if locator not in valid or locator in used_targets:
        return None
    return {
        "op": "set_cell_text",
        "field": field["field"],
        "value": field["value"],
        "target": {
            "table": int(target.get("table")),
            "row": int(target.get("row")),
            "cell": int(target.get("cell")),
        },
        "confidence": float(operation.get("confidence", 0.5) or 0.5),
        "reason": str(operation.get("reason", "")),
    }


def locator_from_target(target: dict[str, Any]) -> str:
    return f"table[{int(target.get('table'))}].row[{int(target.get('row'))}].cell[{int(target.get('cell'))}]"
