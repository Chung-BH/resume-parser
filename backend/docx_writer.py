"""Apply validated operation plans to DOCX files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docx import Document


def apply_operation_plan(template_path: str | Path, plan: dict[str, Any], output_path: str | Path) -> dict[str, Any]:
    document = Document(str(template_path))
    report: list[dict[str, Any]] = []

    for operation in plan.get("operations", []):
        if not isinstance(operation, dict) or operation.get("op") != "set_cell_text":
            continue
        target = operation.get("target", {})
        try:
            table_index = int(target.get("table"))
            row_index = int(target.get("row"))
            cell_index = int(target.get("cell"))
            cell = document.tables[table_index].rows[row_index].cells[cell_index]
        except Exception as exc:  # noqa: BLE001
            report.append({"field": operation.get("field"), "status": "skipped", "message": str(exc)})
            continue
        value = str(operation.get("value", ""))
        write_cell_text(cell, value)
        report.append(
            {
                "field": operation.get("field"),
                "status": "written",
                "value": value,
                "target": target,
            }
        )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    document.save(output)
    return {"docx": str(output), "report": report}


def write_cell_text(cell: Any, value: str) -> None:
    paragraph = cell.paragraphs[0] if cell.paragraphs else cell.add_paragraph()
    if paragraph.runs:
        paragraph.runs[0].text = value
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(value)
    for extra in cell.paragraphs[1:]:
        for run in extra.runs:
            run.text = ""
