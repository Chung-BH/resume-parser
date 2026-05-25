"""Vision-based verification for filled DOCX results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ai_client import OllamaError, generate_json_with_images
from .operation_planner import profile_to_fields
from .vision_analyzer import prepare_vision_images, select_pages


CONFIDENCE_THRESHOLD = 0.72


class ResultVerifier:
    def __init__(self, model: str, ollama_url: str, enabled: bool = True, openai_api_key: str | None = None) -> None:
        self.model = model
        self.ollama_url = ollama_url
        self.enabled = enabled
        self.openai_api_key = openai_api_key

    def verify(
        self,
        final_render: dict[str, Any],
        profile: dict[str, Any],
        operation_plan: dict[str, Any],
        write_report: dict[str, Any],
    ) -> dict[str, Any]:
        pngs = select_pages(final_render.get("pngs", []), max_pages=1)
        expected_fields = profile_to_fields(profile)
        written_fields = [
            item
            for item in write_report.get("report", [])
            if isinstance(item, dict) and item.get("status") == "written"
        ]
        if not operation_plan.get("operations") or not written_fields:
            return no_written_operations_report(expected_fields, pngs)
        if not self.enabled or not pngs:
            return normalize_verification(
                {
                    "status": "skipped",
                    "summary": "vision verification skipped",
                    "field_checks": [],
                    "issues": [],
                },
                expected_fields,
                pngs,
            )

        prompt = build_prompt(expected_fields, operation_plan, written_fields)
        vision_images = prepare_vision_images(pngs, suffix="verify_input")
        try:
            payload = generate_json_with_images(
                prompt,
                vision_images,
                self.model,
                self.ollama_url,
                timeout=150,
                retries=0,
                max_side=640,
                num_predict=1800,
                openai_api_key=self.openai_api_key,
            )
        except OllamaError as exc:
            return written_but_unverified_report(expected_fields, written_fields, pngs, str(exc))
        if not isinstance(payload, dict):
            return written_but_unverified_report(expected_fields, written_fields, pngs, "invalid verification JSON")
        return normalize_verification(payload, expected_fields, pngs)


def no_written_operations_report(expected_fields: list[dict[str, str]], source_images: list[str]) -> dict[str, Any]:
    field_checks = [
        {
            "field": item["field"],
            "expected_value": item["value"],
            "status": "missing",
            "visual_evidence": "No DOCX write operation was applied for this field.",
            "confidence": 0.0,
        }
        for item in expected_fields
    ]
    return {
        "status": "review",
        "overall_confidence": 0.0,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "needs_user_confirmation": True,
        "summary": "적용된 DOCX 작성 작업이 없어 자동 검증을 건너뛰었습니다. 사용자 확인이 필요합니다.",
        "field_checks": field_checks,
        "layout_checks": {
            "cells_intact": True,
            "no_overlap": True,
            "no_obvious_shift": True,
            "confidence": 0.5,
            "notes": "No values were written, so layout damage from writing is unlikely.",
        },
        "missing_fields": [item["field"] for item in expected_fields],
        "issues": [
            {
                "type": "missing_field",
                "field": item["field"],
                "severity": "high",
                "message": f"{item['field']} 필드가 작성되지 않았습니다.",
                "suggested_user_action": "비전 분석 실패 또는 operation plan 실패 원인을 확인하세요.",
            }
            for item in expected_fields
        ],
        "source_images": source_images,
    }


def written_but_unverified_report(
    expected_fields: list[dict[str, str]],
    written_fields: list[dict[str, Any]],
    source_images: list[str],
    error: str,
) -> dict[str, Any]:
    written_names = {str(item.get("field") or "") for item in written_fields}
    field_checks: list[dict[str, Any]] = []
    for item in expected_fields:
        field = item["field"]
        matched = field in written_names or any(name.startswith(f"{field}.") for name in written_names)
        field_checks.append(
            {
                "field": field,
                "expected_value": item["value"],
                "status": "uncertain" if matched else "missing",
                "visual_evidence": "DOCX write operation exists, but vision verification failed." if matched else "No write operation matched this field.",
                "confidence": 0.45 if matched else 0.0,
            }
        )
    missing = [item["field"] for item in field_checks if item["status"] == "missing"]
    return {
        "status": "review",
        "overall_confidence": 0.35 if written_fields else 0.0,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "needs_user_confirmation": True,
        "summary": "DOCX 작성은 수행됐지만 비전 모델 자동 검증이 실패했습니다. 최종 미리보기에서 사용자 확인이 필요합니다.",
        "field_checks": field_checks,
        "layout_checks": {
            "cells_intact": True,
            "no_overlap": True,
            "no_obvious_shift": True,
            "confidence": 0.35,
            "notes": "Visual verification failed, so layout quality could not be confirmed.",
        },
        "missing_fields": missing,
        "issues": [
            {
                "type": "vision_error",
                "field": "",
                "severity": "medium",
                "message": f"비전 모델 자동 검증 실패: {error}",
                "suggested_user_action": "최종 미리보기와 DOCX 파일을 직접 확인하세요.",
            }
        ],
        "source_images": source_images,
    }


def build_prompt(
    expected_fields: list[dict[str, str]],
    operation_plan: dict[str, Any],
    written_fields: list[dict[str, Any]],
) -> str:
    return f"""
Return only one valid JSON object. No markdown.

You are a strict visual QA reviewer for a filled DOCX resume/application form.
You see rendered image(s) of the FINAL filled document.

Verify these things visually and semantically:
- Values are in the correct input areas, not label/header cells.
- Table/cell lines are not broken or obviously shifted.
- Text does not overlap with labels, borders, or other values.
- Expected fields are not missing.
- Long values are readable and not clipped.

Important:
- Do not edit the file.
- Do not invent DOCX operations.
- If you cannot read a value clearly, mark that field as "uncertain" with low confidence.
- Confidence must be a number from 0.0 to 1.0.
- Be conservative. A suspicious placement should lower confidence.

Expected profile fields:
{json.dumps(expected_fields, ensure_ascii=False, indent=2)}

Operations that Python attempted:
{json.dumps(operation_plan.get("operations", []), ensure_ascii=False, indent=2)}

Python write report:
{json.dumps(written_fields, ensure_ascii=False, indent=2)}

Required JSON schema:
{{
  "status": "pass|review|fail",
  "overall_confidence": 0.0,
  "needs_user_confirmation": true,
  "summary": "short Korean summary",
  "field_checks": [
    {{
      "field": "name",
      "expected_value": "김철수",
      "status": "ok|wrong_location|missing|overlap|clipped|uncertain",
      "visual_evidence": "what you see in the rendered image",
      "confidence": 0.0
    }}
  ],
  "layout_checks": {{
    "cells_intact": true,
    "no_overlap": true,
    "no_obvious_shift": true,
    "confidence": 0.0,
    "notes": "short visual layout notes"
  }},
  "missing_fields": ["field names that appear missing"],
  "issues": [
    {{
      "type": "wrong_location|missing_field|overlap|cell_break|clipped_text|uncertain",
      "field": "name or empty",
      "severity": "low|medium|high",
      "message": "Korean issue description",
      "suggested_user_action": "what the user should check"
    }}
  ]
}}
"""


def normalize_verification(
    payload: dict[str, Any],
    expected_fields: list[dict[str, str]],
    source_images: list[str],
) -> dict[str, Any]:
    expected_by_field = {item["field"]: item for item in expected_fields}
    field_checks = normalize_field_checks(payload.get("field_checks"), expected_by_field)
    checked = {item.get("field") for item in field_checks}
    for field in expected_by_field:
        if field not in checked:
            field_checks.append(
                {
                    "field": field,
                    "expected_value": expected_by_field[field]["value"],
                    "status": "missing",
                    "visual_evidence": "verification did not confirm this field",
                    "confidence": 0.0,
                }
            )

    layout_checks = payload.get("layout_checks")
    if not isinstance(layout_checks, dict):
        layout_checks = {}
    layout_confidence = clamp_float(layout_checks.get("confidence"), 0.5)

    issues = normalize_issues(payload.get("issues"))
    missing_fields = sorted(
        {
            str(item.get("field"))
            for item in field_checks
            if item.get("status") in {"missing", "uncertain"} and item.get("field")
        }
        | {str(item) for item in payload.get("missing_fields", []) if item}
    )

    field_confidences = [clamp_float(item.get("confidence"), 0.0) for item in field_checks]
    if field_confidences:
        computed_confidence = (sum(field_confidences) / len(field_confidences) * 0.75) + (layout_confidence * 0.25)
    else:
        computed_confidence = layout_confidence * 0.5
    model_confidence = clamp_float(payload.get("overall_confidence"), computed_confidence)
    overall_confidence = round(min(model_confidence, computed_confidence), 3)

    has_blocking_issue = bool(missing_fields) or any(
        item.get("status") in {"wrong_location", "missing", "overlap", "clipped"}
        for item in field_checks
    ) or any(str(item.get("severity")) == "high" for item in issues)
    needs_user_confirmation = bool(
        payload.get("needs_user_confirmation")
        or overall_confidence < CONFIDENCE_THRESHOLD
        or has_blocking_issue
    )
    status = str(payload.get("status") or "")
    if needs_user_confirmation and status == "pass":
        status = "review"
    if not status:
        status = "review" if needs_user_confirmation else "pass"

    return {
        "status": status,
        "overall_confidence": overall_confidence,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "needs_user_confirmation": needs_user_confirmation,
        "summary": str(payload.get("summary") or ""),
        "field_checks": field_checks,
        "layout_checks": {
            "cells_intact": bool(layout_checks.get("cells_intact", True)),
            "no_overlap": bool(layout_checks.get("no_overlap", True)),
            "no_obvious_shift": bool(layout_checks.get("no_obvious_shift", True)),
            "confidence": layout_confidence,
            "notes": str(layout_checks.get("notes") or ""),
        },
        "missing_fields": missing_fields,
        "issues": issues,
        "source_images": source_images,
    }


def normalize_field_checks(value: Any, expected_by_field: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    allowed = {"ok", "wrong_location", "missing", "overlap", "clipped", "uncertain"}
    checks: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field") or "")
        if not field:
            continue
        status = str(item.get("status") or "uncertain")
        if status not in allowed:
            status = "uncertain"
        checks.append(
            {
                "field": field,
                "expected_value": str(item.get("expected_value") or expected_by_field.get(field, {}).get("value") or ""),
                "status": status,
                "visual_evidence": str(item.get("visual_evidence") or ""),
                "confidence": clamp_float(item.get("confidence"), 0.0),
            }
        )
    return checks


def normalize_issues(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    issues: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        issues.append(
            {
                "type": str(item.get("type") or "uncertain"),
                "field": str(item.get("field") or ""),
                "severity": str(item.get("severity") or "medium"),
                "message": str(item.get("message") or ""),
                "suggested_user_action": str(item.get("suggested_user_action") or ""),
            }
        )
    return issues


def clamp_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))
