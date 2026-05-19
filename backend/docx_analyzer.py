"""DOCX structure extraction for candidate generation."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from docx import Document
from docx.table import _Cell

from .utils import clean_text


LABEL_HINTS = {
    "성명",
    "이름",
    "영문",
    "생년월일",
    "성별",
    "연락처",
    "핸드폰",
    "휴대폰",
    "전화",
    "이메일",
    "email",
    "e-mail",
    "주소",
    "지원직무",
    "직무",
    "학력",
    "학교",
    "경력",
    "자격",
    "병역",
}


def analyze_docx(docx_path: str | Path) -> dict[str, Any]:
    document = Document(str(docx_path))
    tables: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []

    for table_index, table in enumerate(document.tables):
        table_payload: dict[str, Any] = {"table": table_index, "rows": []}
        for row_index, row in enumerate(table.rows):
            groups = visible_cell_groups(row.cells)
            row_texts = [clean_text(row.cells[group["start"]].text) for group in groups]
            row_payload: dict[str, Any] = {"row": row_index, "cells": []}
            for group in groups:
                cell_index = group["start"]
                cell = row.cells[cell_index]
                text = clean_text(cell.text)
                payload = {
                    "locator": f"table[{table_index}].row[{row_index}].cell[{cell_index}]",
                    "table": table_index,
                    "row": row_index,
                    "cell": cell_index,
                    "span_start": group["start"],
                    "span_end": group["end"],
                    "text": text,
                    "normalized_text": normalize_text(text),
                    "left_text": nearest_text(groups, row.cells, cell_index, direction="left"),
                    "right_text": nearest_text(groups, row.cells, cell_index, direction="right"),
                    "row_texts": row_texts,
                    "is_empty": not text,
                    "is_label_candidate": is_label(text),
                    "is_input_candidate": is_input_candidate(text),
                }
                row_payload["cells"].append(payload)
                if payload["is_label_candidate"]:
                    labels.append(payload)
                if payload["is_input_candidate"]:
                    candidates.append(payload)
            table_payload["rows"].append(row_payload)
        tables.append(table_payload)

    return {
        "tables": tables,
        "labels": labels,
        "input_candidates": candidates,
        "summary": {
            "table_count": len(tables),
            "label_count": len(labels),
            "candidate_count": len(candidates),
        },
    }


def visible_cell_groups(cells: list[_Cell]) -> list[dict[str, int]]:
    if not cells:
        return []
    groups: list[dict[str, int]] = []
    start = 0
    last = id(cells[0]._tc)
    for index, cell in enumerate(cells[1:], start=1):
        current = id(cell._tc)
        if current != last:
            groups.append({"start": start, "end": index - 1})
            start = index
            last = current
    groups.append({"start": start, "end": len(cells) - 1})
    return groups


def nearest_text(groups: list[dict[str, int]], cells: list[_Cell], cell_index: int, direction: str) -> str:
    if direction == "left":
        iterable = reversed([group for group in groups if group["end"] < cell_index])
    else:
        iterable = [group for group in groups if group["start"] > cell_index]
    for group in iterable:
        text = clean_text(cells[group["start"]].text)
        if text:
            return text
    return ""


def is_label(text: str) -> bool:
    normalized = normalize_text(text).lower()
    return bool(normalized) and any(normalize_text(hint).lower() in normalized for hint in LABEL_HINTS)


def is_input_candidate(text: str) -> bool:
    cleaned = clean_text(text)
    normalized = normalize_text(cleaned)
    return not cleaned or normalized in {"-", "년월일", "()", "상()중()하()"}


def normalize_text(text: str) -> str:
    return re.sub(r"[\s|]+", "", text or "")
