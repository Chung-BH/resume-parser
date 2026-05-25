"""Operation plan generation.

LLMs only generate JSON plans. Python validates and applies them.
"""

from __future__ import annotations

import json
from typing import Any

from .ai_client import OllamaError, generate_json
from .record_planner import (
    build_record_prompt,
    field_aliases as record_field_aliases,
    normalize_record_operations,
    select_record_candidates,
    split_record_fields,
)
from .utils import clean_text


class OperationPlanner:
    def __init__(self, model: str, ollama_url: str, enabled: bool = True, openai_api_key: str | None = None) -> None:
        self.model = model
        self.ollama_url = ollama_url
        self.enabled = enabled
        self.openai_api_key = openai_api_key

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
            errors.append("Vision analysis unavailable; text planner used DOCX layout JSON only.")
        used_targets: set[str] = set()
        scalar_fields, record_groups = split_record_fields(fields)
        for field in scalar_fields:
            try:
                payload = generate_json(
                    build_prompt(field, layout, vision, used_targets),
                    self.model,
                    self.ollama_url,
                    timeout=45,
                    openai_api_key=self.openai_api_key,
                )
            except OllamaError as exc:
                errors.append(f"{field['field']}: {exc}")
                continue
            op = normalize_operation(payload, field, layout, used_targets)
            if op:
                used_targets.add(locator_from_target(op["target"]))
                operations.append(op)
        for record_key, record_fields in record_groups:
            vision_candidates = relevant_vision_candidates(vision, record_key)
            record_candidates = select_record_candidates(layout, record_key, record_fields, vision_candidates, used_targets)
            try:
                payload = generate_json(
                    build_record_prompt(record_key, record_fields, layout, vision, vision_candidates, record_candidates, field_intent),
                    self.model,
                    self.ollama_url,
                    timeout=75,
                    openai_api_key=self.openai_api_key,
                )
            except OllamaError as exc:
                errors.append(f"{record_key}: {exc}")
                continue
            valid_locators = {item["locator"] for item in layout.get("input_candidates", []) if isinstance(item, dict)}
            record_ops = normalize_record_operations(payload, record_fields, valid_locators, used_targets, record_candidates)
            for op in record_ops:
                used_targets.add(locator_from_target(op["target"]))
                operations.append(op)
        return {
            "operations": operations,
            "summary": f"Generated {len(operations)} operations from {len(fields)} profile fields.",
            "status": "planned" if operations else "no_operations",
            "errors": errors,
        }


def build_prompt(field: dict[str, str], layout: dict[str, Any], vision: dict[str, Any], used_targets: set[str]) -> str:
    all_candidates = [
        item
        for item in layout.get("input_candidates", [])[:280]
        if isinstance(item, dict) and item.get("locator") not in used_targets
    ]
    vision_candidates = relevant_vision_candidates(vision, field["field"])
    candidates = relevant_layout_candidates(all_candidates, field["field"], vision_candidates)
    if not candidates:
        return f"""
Return only valid JSON.

No reliable DOCX input candidates were found for this field, so do not guess.

FIELD:
{json.dumps(field, ensure_ascii=False, indent=2)}

Return exactly:
{{"operation": null, "summary": "no reliable DOCX input candidate"}}
"""
    compact_layout = {
        "summary": layout.get("summary", {}),
        "labels": layout.get("labels", [])[:120],
        "input_candidates": candidates,
    }
    compact_vision = {
        "status": vision.get("status"),
        "document_summary": vision.get("document_summary"),
        "summary": vision.get("summary"),
        "visual_fields": vision_candidates,
        "warnings": vision.get("warnings", [])[:30],
    }
    suggested_target = candidate_target(candidates[0]) if candidates else {"table": 0, "row": 0, "cell": 0}
    return f"""
Return only valid JSON.

You generate ONE DOCX operation for a local document agent.
You do not edit files. Python will apply your JSON operation.

Hard constraints:
- Choose at most one existing DOCX input candidate.
- target must correspond to one locator from DOCX_LAYOUT.input_candidates.
- Choose target numbers by reading one DOCX_LAYOUT.input_candidates item. Do not copy example numbers from this prompt.
- Do not choose label cells.
- Do not invent cells, rows, tables, placeholders, or coordinates.
- If uncertain, return {{"operation": null, "summary": "reason"}}.

How to use VISION:
- VISION.visual_fields is semantic visual evidence from rendered page images and crops.
- Prefer targets whose DOCX row_texts/left_text/right_text match VISION.visual_fields.label_seen and nearby_text.
- Use crop_id, relative_position, and target_area as supporting evidence when several DOCX candidates look similar.
- If VISION says the target is a blank area right/below a visible label, choose a DOCX input candidate in the same row/section, not the label cell.
- If VISION is failed/skipped/unavailable, use DOCX_LAYOUT labels and input_candidates.
- If DOCX_LAYOUT and successful VISION conflict, choose no operation instead of guessing.
- Your reason must mention both DOCX evidence and visual semantic evidence.

FIELD:
{json.dumps(field, ensure_ascii=False, indent=2)}

FIELD_INTENT:
{json.dumps(field_intent(field["field"]), ensure_ascii=False)}

DOCX_LAYOUT:
{json.dumps(compact_layout, ensure_ascii=False, indent=2)}

VISION:
{json.dumps(compact_vision, ensure_ascii=False, indent=2)}

Return exactly this JSON shape and nothing else.
Do not return FIELD, DOCX_LAYOUT, or VISION.
Do not copy input JSON.

{{
  "operation": {{
    "op": "set_cell_text",
    "field": "{field['field']}",
    "value": {json.dumps(field['value'], ensure_ascii=False)},
    "target": {json.dumps(suggested_target, ensure_ascii=False)},
    "confidence": 0.8,
    "reason": "specific DOCX evidence and specific visual evidence"
  }},
  "summary": "short summary"
}}
"""


def candidate_target(candidate: dict[str, Any]) -> dict[str, int]:
    return {
        "table": int(candidate.get("table", 0)),
        "row": int(candidate.get("row", 0)),
        "cell": int(candidate.get("cell", 0)),
    }


def relevant_vision_candidates(vision: dict[str, Any], field: str) -> list[dict[str, Any]]:
    base = field.split("[", 1)[0]
    candidates = vision.get("visual_fields") or vision.get("field_candidates") or vision.get("fields") or []
    if not isinstance(candidates, list):
        return []
    relevant: list[dict[str, Any]] = []
    aliases = field_aliases(field)
    for item in candidates:
        if not isinstance(item, dict):
            continue
        item_field = str(item.get("field") or "")
        evidence = " ".join(
            [
                str(item.get("label_seen") or ""),
                str(item.get("target_area") or ""),
                str(item.get("relative_position") or ""),
            ]
        ).lower()
        if item_field == field or item_field == base or item_field.startswith(base):
            relevant.append(item)
        elif any(alias.lower() in evidence for alias in aliases):
            relevant.append(item)
    if relevant:
        return relevant[:20]
    return []


def relevant_layout_candidates(
    candidates: list[dict[str, Any]],
    field: str,
    vision_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    terms = field_aliases(field)
    for item in vision_candidates:
        terms.append(str(item.get("label_seen") or ""))
    normalized_terms = {normalize_match_text(term) for term in terms if normalize_match_text(term)}
    matched = [
        item
        for item in candidates
        if normalized_terms and any(term in candidate_evidence(item) for term in normalized_terms)
    ]
    if matched:
        matched.sort(key=lambda item: candidate_match_score(item, normalized_terms), reverse=True)
    return matched[:40]


def candidate_match_score(candidate: dict[str, Any], terms: set[str]) -> int:
    left = normalize_match_text(str(candidate.get("left_text") or ""))
    right = normalize_match_text(str(candidate.get("right_text") or ""))
    rows = normalize_match_text(
        " ".join(str(value) for value in candidate.get("row_texts", []) if value)
        if isinstance(candidate.get("row_texts"), list)
        else ""
    )
    score = 0
    if any(term in left for term in terms):
        score += 30
    if any(term in right for term in terms):
        score += 10
    if any(term in rows for term in terms):
        score += 1
    return score


def candidate_evidence(candidate: dict[str, Any]) -> str:
    texts = [
        str(candidate.get("left_text") or ""),
        str(candidate.get("right_text") or ""),
        " ".join(str(value) for value in candidate.get("row_texts", []) if value)
        if isinstance(candidate.get("row_texts"), list)
        else "",
    ]
    return normalize_match_text(" ".join(texts))


def normalize_match_text(value: str) -> str:
    return "".join(str(value or "").lower().split())


def field_aliases(field: str) -> list[str]:
    base = field.split("[", 1)[0]
    if base in {"education", "careers", "certificates", "languages", "military"}:
        return record_field_aliases(field)
    aliases = {
        "name": ["성명", "이름", "성 명"],
        "english_name": ["영문", "영문명", "영문 이름", "영문성명"],
        "birth_date": ["생년월일", "생일", "출생"],
        "gender": ["성별", "남", "여"],
        "phone": ["연락처", "핸드폰", "휴대폰", "전화", "mobile", "phone"],
        "email": ["이메일", "e-mail", "email"],
        "address": ["주소"],
        "job": ["지원직무", "직무", "지원 분야"],
    }
    return aliases.get(base, [field])


def field_detail(field: str) -> str:
    return field.rsplit(".", 1)[1] if "." in field else ""


def profile_to_fields(profile: dict[str, Any]) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    for key in ["name", "english_name", "birth_date", "gender", "phone", "email", "address", "job"]:
        value = clean_text(profile.get(key))
        if value:
            fields.append({"field": key, "value": value})
    for index, row in enumerate(profile.get("education", []) or []):
        fields.extend(row_to_fields(f"education[{index}]", row, ["period", "school", "major"]))
    for index, row in enumerate(profile.get("careers", []) or []):
        fields.extend(row_to_fields(f"careers[{index}]", row, ["period", "company", "position", "role"]))
    for index, row in enumerate(profile.get("certificates", []) or []):
        fields.extend(row_to_fields(f"certificates[{index}]", row, ["name", "issuer", "date"]))
    for index, row in enumerate(profile.get("languages", []) or []):
        fields.extend(row_to_fields(f"languages[{index}]", row, ["language", "ability", "test", "score"]))
    for index, row in enumerate(profile.get("military", []) or []):
        fields.extend(row_to_fields(f"military[{index}]", row, ["status", "branch", "service_type", "rank", "period", "exemption_reason"]))
    return fields


def row_to_fields(prefix: str, row: Any, keys: list[str]) -> list[dict[str, str]]:
    if isinstance(row, dict):
        return [
            {"field": f"{prefix}.{key}", "value": clean_text(row.get(key))}
            for key in keys
            if clean_text(row.get(key))
        ]
    value = row_to_value(row, keys)
    return [{"field": prefix, "value": value}] if value else []


def row_to_value(row: Any, keys: list[str]) -> str:
    if isinstance(row, str):
        return clean_text(row)
    if isinstance(row, dict):
        return " / ".join(clean_text(row.get(key)) for key in keys if clean_text(row.get(key)))
    return ""


def field_intent(field: str) -> str:
    base = field.split("[", 1)[0]
    detail = field_detail(field)
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
        "languages": "Foreign language entry; likely in 외국어 section.",
        "military": "Military service entry; likely in 병역 section.",
    }
    detail_intents = {
        "period": "period/date-range column",
        "school": "school name column",
        "major": "major/department column",
        "company": "company/employer column",
        "position": "position/title column",
        "role": "role/duties/content column",
        "name": "name/type/title column",
        "issuer": "issuer/organization column",
        "date": "date/acquired date column",
        "language": "foreign language name column",
        "ability": "language ability/proficiency column",
        "test": "language test name column",
        "score": "official score/grade column",
        "status": "military service status/category column",
        "branch": "military branch column",
        "service_type": "service type column",
        "rank": "rank column",
        "exemption_reason": "exemption reason column",
    }
    base_intent = intents.get(base, field)
    if detail:
        return f"{base_intent} Use the {detail_intents.get(detail, detail)}."
    return base_intent


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
