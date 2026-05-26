"""End-to-end processing pipeline."""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

from .docx_analyzer import analyze_docx
from .docx_writer import apply_operation_plan
from .operation_planner import OperationPlanner
from .profile_parser import ProfileParser, normalize_profile
from .renderer import render_docx
from .result_verifier import ResultVerifier
from .utils import timestamp, write_json
from .vision_analyzer import VisionAnalyzer


def run_pipeline(
    template_path: str | Path,
    user_text: str,
    output_root: str | Path,
    text_model: str,
    vision_model: str,
    ollama_url: str,
    use_final_verification: bool = True,
    use_ai: bool = True,
    profile_payload: dict[str, Any] | None = None,
    openai_api_key: str | None = None,
) -> dict[str, Any]:
    run_dir = Path(output_root) / f"run_{timestamp()}_{uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    template = Path(template_path)
    copied_template = run_dir / "template.docx"
    shutil.copy2(template, copied_template)

    logs: list[str] = []

    def step(message: str) -> None:
        logs.append(message)

    if profile_payload is not None:
        step("[1/8] 입력 정보 정리")
        profile = normalize_profile(profile_payload)
    else:
        step(f"[1/8] {text_model}로 입력 문장 정리")
        profile = ProfileParser(text_model, ollama_url, use_ai=use_ai, openai_api_key=openai_api_key).parse(user_text)
    write_json(run_dir / "profile.json", profile)

    step("[2/8] 문서 구조와 빈칸 후보 분석")
    layout = analyze_docx(copied_template)
    write_json(run_dir / "layout.json", layout)

    step("[3/8] 원본 문서 미리보기 생성")
    original_render = render_docx(copied_template, run_dir / "original_preview", prefix="original")
    write_json(run_dir / "original_render.json", original_render)

    step(f"[4/8] {vision_model}로 라벨과 빈칸 위치 확인")
    vision = VisionAnalyzer(vision_model, ollama_url, enabled=True, openai_api_key=openai_api_key).analyze(original_render, profile)
    write_json(run_dir / "vision_fields.json", vision)

    step(f"[5/8] {text_model}로 입력값을 넣을 칸 결정")
    plan = OperationPlanner(text_model, ollama_url, enabled=use_ai, openai_api_key=openai_api_key).plan(profile, layout, vision)
    write_json(run_dir / "operation_plan.json", plan)

    step("[6/8] DOCX에 입력값 작성")
    final_docx = run_dir / "final.docx"
    write_report = apply_operation_plan(copied_template, plan, final_docx)
    write_json(run_dir / "write_report.json", write_report)

    step("[7/8] 작성 결과 미리보기 생성")
    final_render = render_docx(final_docx, run_dir / "final_preview", prefix="final")
    write_json(run_dir / "final_render.json", final_render)

    if use_final_verification:
        step(f"[8/8] {vision_model}로 최종 결과 확인")
    else:
        step("[8/8] 최종 비전 검증 건너뜀")
    verification_report = ResultVerifier(vision_model, ollama_url, enabled=use_final_verification, openai_api_key=openai_api_key).verify(
        final_render=final_render,
        profile=profile,
        operation_plan=plan,
        write_report=write_report,
    )
    write_json(run_dir / "verification_report.json", verification_report)

    result = {
        "run_dir": str(run_dir),
        "logs": logs,
        "profile": profile,
        "layout_summary": layout.get("summary", {}),
        "vision": vision,
        "operation_plan": plan,
        "write_report": write_report,
        "verification_report": verification_report,
        "original_render": original_render,
        "final_render": final_render,
        "final_docx": str(final_docx),
        "final_pdf": final_render.get("pdf"),
        "preview_pngs": final_render.get("pngs", []),
        "warnings": collect_warnings(original_render, final_render, vision, verification_report),
    }
    write_json(run_dir / "result.json", result)
    return result


def collect_warnings(*payloads: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for item in payload.get("warnings", []):
            warnings.append(str(item))
        if payload.get("needs_user_confirmation") and payload.get("status") != "skipped":
            warnings.append("검증 confidence가 낮아 사용자 확인이 필요합니다.")
        for issue in payload.get("issues", []):
            if isinstance(issue, dict) and issue.get("message"):
                warnings.append(str(issue["message"]))
    return warnings
