"""Record-group planning helpers for repeated resume sections."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from .utils import clean_text


def split_record_fields(fields: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[tuple[str, list[dict[str, str]]]]]:
    scalar_fields: list[dict[str, str]] = []
    grouped: dict[str, list[dict[str, str]]] = {}
    order: list[str] = []
    for field in fields:
        key = record_group_key(field["field"])
        if not key:
            scalar_fields.append(field)
            continue
        grouped.setdefault(key, [])
        if key not in order:
            order.append(key)
        grouped[key].append(field)
    return scalar_fields, [(key, grouped[key]) for key in order]


def record_group_key(field: str) -> str | None:
    match = re.match(r"^([a-z_]+\[\d+\])\.[a-z_]+$", field)
    return match.group(1) if match else None


def select_record_candidates(
    layout: dict[str, Any],
    record_key: str,
    record_fields: list[dict[str, str]],
    vision_candidates: list[dict[str, Any]],
    used_targets: set[str],
) -> list[dict[str, Any]]:
    candidates = [
        item
        for item in layout.get("input_candidates", [])[:320]
        if isinstance(item, dict) and item.get("locator") not in used_targets
    ]
    section = record_key.split("[", 1)[0]
    index = record_index(record_key)
    terms = field_aliases(section)
    for field in record_fields:
        terms.extend(field_aliases(field["field"]))
    for item in vision_candidates:
        terms.append(str(item.get("label_seen") or ""))
        nearby = item.get("nearby_text", [])
        if isinstance(nearby, list):
            terms.extend(str(value) for value in nearby if value)

    normalized_terms = {norm(term) for term in terms if norm(term)}
    matched = [
        item
        for item in candidates
        if normalized_terms and any(term in candidate_evidence(item) for term in normalized_terms)
    ]
    if not matched:
        return []

    section_terms = {norm(term) for term in field_aliases(section)}
    section_matched = [item for item in matched if any(term in candidate_evidence(item) for term in section_terms)] or matched
    rows = drop_header_rows(group_by_row(section_matched), section)
    if not rows:
        return []

    if section == "languages":
        language = next(
            (field["value"] for field in record_fields if field_detail(field["field"]) == "language" and field.get("value")),
            "",
        )
        selected = find_row_with_text(rows, language)
        if not selected or not useful_language_row(selected, language):
            selected = first_language_input_row(rows)
    else:
        rows.sort(key=lambda row: (-row_score(row, section), int(row[0].get("table", 0)), int(row[0].get("row", 0))))
        good = [row for row in rows if row_score(row, section) > 0] or rows
        good.sort(key=lambda row: (int(row[0].get("table", 0)), int(row[0].get("row", 0))))
        selected = good[min(index, len(good) - 1)]

    filtered = filter_section_columns(selected, section, record_fields) or selected
    annotated = annotate_column_headers(filtered, layout)
    return sorted(annotated, key=lambda item: (int(item.get("table", 0)), int(item.get("row", 0)), int(item.get("cell", 0))))[:40]


def build_record_prompt(
    record_key: str,
    record_fields: list[dict[str, str]],
    layout: dict[str, Any],
    vision: dict[str, Any],
    vision_candidates: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    field_intent: Callable[[str], str],
) -> str:
    if not candidates:
        return f"""
Return only valid JSON.

No reliable DOCX record group candidates were found for this record, so do not guess.

RECORD:
{json.dumps({"record": record_key, "fields": record_fields}, ensure_ascii=False, indent=2)}

Return exactly:
{{"operations": [], "summary": "no reliable DOCX record group"}}
"""

    return f"""
Return only valid JSON.

You generate DOCX operations for ONE logical record group in a resume/application form.
Python will apply your JSON operations.

Record anchoring:
- First identify the visual record group for RECORD_KEY.
- All operations for this record must stay inside that same visual record group.
- Use column_header when present to distinguish period, school, major, issuer, date, test, score, and similar subfields.
- If the field value already appears as a fixed row label inside the chosen record group, omit that field instead of duplicating it into a blank cell.
- If you cannot place a field inside the chosen record group, omit that field.

Hard constraints:
- Every target must correspond to one locator from DOCX_LAYOUT.input_candidates.
- Do not choose label/header cells.
- Do not invent cells, rows, tables, placeholders, or coordinates.
- If uncertain about the whole record, return {{"operations": [], "summary": "reason"}}.

RECORD_KEY:
{record_key}

RECORD_FIELDS:
{json.dumps(record_fields, ensure_ascii=False, indent=2)}

FIELD_INTENTS:
{json.dumps({field["field"]: field_intent(field["field"]) for field in record_fields}, ensure_ascii=False, indent=2)}

DOCX_LAYOUT:
{json.dumps({"summary": layout.get("summary", {}), "input_candidates": candidates}, ensure_ascii=False, indent=2)}

VISION:
{json.dumps({
    "status": vision.get("status"),
    "document_summary": vision.get("document_summary"),
    "visual_fields": vision_candidates,
    "warnings": vision.get("warnings", [])[:30],
}, ensure_ascii=False, indent=2)}

Return exactly this JSON shape and nothing else:
{{
  "operations": {json.dumps(example_operations(record_fields, candidates), ensure_ascii=False)},
  "summary": "short summary"
}}
"""


def normalize_record_operations(
    payload: Any,
    record_fields: list[dict[str, str]],
    valid_locators: set[str],
    used_targets: set[str],
    allowed_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("operations"), list):
        return []
    expected = {field["field"]: field for field in record_fields}
    allowed = {str(item.get("locator")) for item in allowed_candidates if isinstance(item, dict) and item.get("locator")}
    normalized: list[dict[str, Any]] = []
    local_used = set(used_targets)
    for operation in payload["operations"]:
        if not isinstance(operation, dict):
            continue
        field = expected.get(str(operation.get("field") or ""))
        target = operation.get("target")
        if not field or not isinstance(target, dict):
            continue
        if field_detail(field["field"]) == "language" and visible_near_candidates(field["value"], allowed_candidates):
            continue
        try:
            locator = locator_from_target(target)
        except (TypeError, ValueError):
            continue
        if locator not in valid_locators or locator in local_used or (allowed and locator not in allowed):
            continue
        local_used.add(locator)
        normalized.append(
            {
                "op": "set_cell_text",
                "field": field["field"],
                "value": field["value"],
                "target": {"table": int(target["table"]), "row": int(target["row"]), "cell": int(target["cell"])},
                "confidence": float(operation.get("confidence", 0.5) or 0.5),
                "reason": str(operation.get("reason", "")),
            }
        )
    return normalized if same_record_group(normalized) else []


def example_operations(record_fields: list[dict[str, str]], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    used: set[str] = set()
    for field in record_fields:
        if field_detail(field["field"]) == "language" and visible_near_candidates(field["value"], candidates):
            continue
        candidate = best_column_candidate(field["field"], candidates, used)
        if not candidate:
            continue
        used.add(str(candidate.get("locator")))
        operations.append(
            {
                "op": "set_cell_text",
                "field": field["field"],
                "value": field["value"],
                "target": candidate_target(candidate),
                "confidence": 0.8,
                "reason": "same visual record group and matching column evidence",
            }
        )
    return operations


def best_column_candidate(field: str, candidates: list[dict[str, Any]], used: set[str]) -> dict[str, Any] | None:
    scored = [
        (column_score(field, candidate), candidate)
        for candidate in candidates
        if str(candidate.get("locator")) not in used
    ]
    scored = [(score, candidate) for score, candidate in scored if score > 0]
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], int(item[1].get("cell", 0))))
    return scored[0][1]


def column_score(field: str, candidate: dict[str, Any]) -> int:
    terms = {norm(term) for term in column_aliases(field)}
    header = norm(str(candidate.get("column_header") or ""))
    neighbor = candidate_neighbors(candidate)
    score = (50 if any(term and term in header for term in terms) else 0) + (
        12 if any(term and term in neighbor for term in terms) else 0
    )
    if field.startswith("education") and field_detail(field) == "period" and norm(str(candidate.get("text") or "")) == "-":
        score += 8
    return score


def column_aliases(field: str) -> list[str]:
    base = field.split("[", 1)[0]
    detail = field_detail(field)
    extra = {
        ("education", "period"): ["기간", "입학년월", "졸업년월", "재학기간"],
        ("education", "school"): ["학교명", "출신학교", "학교"],
        ("education", "major"): ["전공", "학과", "학과(전공)"],
        ("careers", "period"): ["근무기간", "기간"],
        ("careers", "company"): ["근무처", "회사"],
        ("careers", "position"): ["직위", "직책"],
        ("careers", "role"): ["직무", "담당업무", "업무"],
        ("certificates", "name"): ["특수자격및면허", "종류 및 등급", "자격증", "자격명"],
        ("certificates", "issuer"): ["발행처", "발급처", "기관"],
        ("certificates", "date"): ["취득일", "취득일자", "일자"],
        ("languages", "ability"): ["활용능력", "능력", "상", "중", "하"],
        ("languages", "test"): ["테스트명", "시험명", "시험", "TOEIC", "TOEFL", "JLPT", "HSK"],
        ("languages", "score"): ["공인점수", "점수", "점(급)", "급"],
        ("military", "status"): ["구분", "병역구분", "복무구분"],
        ("military", "branch"): ["군별"],
        ("military", "service_type"): ["역종"],
        ("military", "rank"): ["계급"],
        ("military", "period"): ["복무기간", "기간"],
        ("military", "exemption_reason"): ["면제사유", "사유"],
    }
    return field_aliases(field) + extra.get((base, detail), [])


def field_aliases(field: str) -> list[str]:
    base = field.split("[", 1)[0]
    detail = field_detail(field)
    section = {
        "education": ["학력", "학교", "전공"],
        "careers": ["경력", "회사", "근무"],
        "certificates": ["자격", "자격증", "면허"],
        "languages": ["외국어", "외국어명", "활용능력", "테스트명", "공인점수", "어학", "언어"],
        "military": ["병역", "병역구분", "군별", "역종", "계급", "복무기간", "면제사유"],
    }
    detail_terms = {
        ("education", "period"): ["기간", "기 간"],
        ("education", "school"): ["출신학교", "출 신 학 교", "학교", "고등학교", "대학교", "대학원"],
        ("education", "major"): ["학과", "학과(전공)", "전공"],
        ("careers", "period"): ["기간", "기 간"],
        ("careers", "company"): ["회사", "근무처", "직장명"],
        ("careers", "position"): ["직위", "직책", "직급"],
        ("careers", "role"): ["담당업무", "업무", "내용"],
        ("certificates", "name"): ["종류 및 등급", "자격증", "자격명", "종류"],
        ("certificates", "issuer"): ["발행처", "발급처", "기관"],
        ("certificates", "date"): ["취득일", "취득일자", "일자"],
        ("languages", "language"): ["외국어명", "외국어", "언어"],
        ("languages", "ability"): ["활용능력", "능력", "상", "중", "하"],
        ("languages", "test"): ["테스트명", "시험명", "시험", "TOEIC", "TOEFL", "JLPT", "HSK"],
        ("languages", "score"): ["공인점수", "점수", "점(급)", "급"],
        ("military", "status"): ["구분", "병역구분", "복무구분"],
        ("military", "branch"): ["군별"],
        ("military", "service_type"): ["역종"],
        ("military", "rank"): ["계급"],
        ("military", "period"): ["복무기간", "기간"],
        ("military", "exemption_reason"): ["면제사유", "사유"],
    }
    return detail_terms.get((base, detail), section.get(base, [field]))


def annotate_column_headers(candidates: list[dict[str, Any]], layout: dict[str, Any]) -> list[dict[str, Any]]:
    tables = layout.get("tables", [])
    if not isinstance(tables, list):
        return candidates
    annotated: list[dict[str, Any]] = []
    for candidate in candidates:
        item = dict(candidate)
        item["column_header"] = nearest_column_header(item, tables)
        annotated.append(item)
    return annotated


def nearest_column_header(candidate: dict[str, Any], tables: list[Any]) -> str:
    table_index = int(candidate.get("table", 0))
    row_index = int(candidate.get("row", 0))
    cell_index = int(candidate.get("cell", 0))
    if table_index >= len(tables) or not isinstance(tables[table_index], dict):
        return ""
    for row in reversed(tables[table_index].get("rows", [])[:row_index]):
        for cell in row.get("cells", []):
            start = int(cell.get("span_start", cell.get("cell", 0)))
            end = int(cell.get("span_end", cell.get("cell", 0)))
            text = clean_text(cell.get("text"))
            if text and start <= cell_index <= end:
                return text
    return ""


def group_by_row(candidates: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for item in candidates:
        grouped.setdefault((int(item.get("table", 0)), int(item.get("row", 0))), []).append(item)
    return [sorted(row, key=lambda item: int(item.get("cell", 0))) for _, row in sorted(grouped.items())]


def drop_header_rows(rows: list[list[dict[str, Any]]], section: str) -> list[list[dict[str, Any]]]:
    if section != "certificates" or len(rows) < 2:
        return rows
    header_terms = {norm(term) for term in ["특수자격및면허", "등급", "종류 및 등급"]}
    filtered = [row for row in rows if not any(term and term in norm(" ".join(row_texts(row))) for term in header_terms)]
    return filtered or rows


def filter_section_columns(row: list[dict[str, Any]], section: str, record_fields: list[dict[str, str]]) -> list[dict[str, Any]]:
    if section == "certificates":
        terms = {norm(term) for term in field_aliases(section)}
        return [item for item in row if any(term and term in candidate_neighbors(item) for term in terms)]
    if section == "languages":
        return [item for item in row if is_language_input_candidate(item)]
    return row


def useful_language_row(row: list[dict[str, Any]], language: str) -> bool:
    row_value = norm(" ".join(row_texts(row)))
    language_term = norm(language)
    if not any(is_language_input_candidate(item) for item in row):
        return False
    if language_term and language_term in row_value:
        return True
    return len([item for item in row if is_language_input_candidate(item)]) >= 3


def first_language_input_row(rows: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    for row in rows:
        candidates = [item for item in row if is_language_input_candidate(item)]
        if len(candidates) >= 3:
            return row
    for row in rows:
        if any(is_language_input_candidate(item) for item in row):
            return row
    return rows[0] if rows else []


def is_language_input_candidate(candidate: dict[str, Any]) -> bool:
    left = norm(str(candidate.get("left_text") or ""))
    text = norm(str(candidate.get("text") or ""))
    row_value = candidate_evidence(candidate)
    if any(term in left or term in text for term in ["msword", "msexcel", "msppt", "ms-word", "ms-excel", "ms-ppt"]):
        return False
    if "컴퓨터" in left or "컴퓨터" in text:
        return False
    if "외국어" in left or "어학" in left or "외국어" in row_value or "어학" in row_value:
        return True
    return False


def find_row_with_text(rows: list[list[dict[str, Any]]], value: str) -> list[dict[str, Any]]:
    value_text = norm(value)
    if not value_text:
        return rows[0] if rows else []
    for row in rows:
        if value_text in norm(" ".join(row_texts(row))):
            return row
    return rows[0] if rows else []


def row_score(row: list[dict[str, Any]], section: str) -> int:
    evidence = norm(" ".join(row_texts(row)))
    score = len(row)
    if any(norm(term) in evidence for term in field_aliases(section)):
        score += 20
    for other in {"education", "careers", "certificates", "languages", "military"} - {section}:
        if any(norm(term) in evidence for term in field_aliases(other)):
            score -= 8
    return score


def row_texts(row: list[dict[str, Any]]) -> list[str]:
    texts: list[str] = []
    for item in row:
        texts.extend([str(item.get("left_text") or ""), str(item.get("right_text") or ""), str(item.get("text") or "")])
        if isinstance(item.get("row_texts"), list):
            texts.extend(str(value) for value in item["row_texts"] if value)
    return [text for text in texts if text]


def candidate_evidence(candidate: dict[str, Any]) -> str:
    row_values = candidate.get("row_texts", [])
    return norm(
        " ".join(
            [
                str(candidate.get("left_text") or ""),
                str(candidate.get("right_text") or ""),
                " ".join(str(value) for value in row_values if value) if isinstance(row_values, list) else "",
            ]
        )
    )


def candidate_neighbors(candidate: dict[str, Any]) -> str:
    return norm(" ".join([str(candidate.get("left_text") or ""), str(candidate.get("right_text") or ""), str(candidate.get("text") or "")]))


def candidate_target(candidate: dict[str, Any]) -> dict[str, int]:
    return {"table": int(candidate.get("table", 0)), "row": int(candidate.get("row", 0)), "cell": int(candidate.get("cell", 0))}


def visible_near_candidates(value: str, candidates: list[dict[str, Any]]) -> bool:
    value_text = norm(value)
    return bool(value_text) and any(value_text in candidate_neighbors(item) for item in candidates if isinstance(item, dict))


def same_record_group(operations: list[dict[str, Any]]) -> bool:
    if len(operations) < 2:
        return True
    targets = [operation["target"] for operation in operations]
    if len({int(target["table"]) for target in targets}) != 1:
        return False
    rows = [int(target["row"]) for target in targets]
    return max(rows) - min(rows) <= max(2, len(rows) - 1)


def record_index(record_key: str) -> int:
    match = re.search(r"\[(\d+)\]", record_key)
    return int(match.group(1)) if match else 0


def field_detail(field: str) -> str:
    return field.rsplit(".", 1)[1] if "." in field else ""


def locator_from_target(target: dict[str, Any]) -> str:
    return f"table[{int(target.get('table'))}].row[{int(target.get('row'))}].cell[{int(target.get('cell'))}]"


def norm(value: str) -> str:
    return "".join(str(value or "").lower().split())
