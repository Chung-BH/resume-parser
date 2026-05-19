"""Shared schemas and defaults."""

from __future__ import annotations

from typing import Any


PROFILE_SCHEMA: dict[str, Any] = {
    "name": "",
    "english_name": "",
    "birth_date": "",
    "gender": "",
    "phone": "",
    "email": "",
    "address": "",
    "job": "",
    "education": [],
    "careers": [],
    "certificates": [],
    "extra": {},
}


OPERATION_PLAN_SCHEMA: dict[str, Any] = {
    "operations": [
        {
            "op": "set_cell_text",
            "field": "name",
            "value": "김철수",
            "target": {"table": 0, "row": 0, "cell": 1},
            "confidence": 0.8,
            "reason": "The target cell is a blank input cell near the visible name label.",
        }
    ],
    "summary": "short Korean summary",
}
