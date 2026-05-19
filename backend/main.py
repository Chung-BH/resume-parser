"""FastAPI app."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("FastAPI dependencies are missing. Run: pip install -r requirements.txt") from exc

from .ollama_client import list_models
from .pipeline import run_pipeline
from .utils import safe_filename


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = ROOT / "outputs"

app = FastAPI(title="Local DOCX Agent MVP")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok"}


@app.get("/api/models")
def models(ollama_url: str = "http://localhost:11434") -> dict[str, Any]:
    return {"models": list_models(ollama_url)}


@app.post("/api/process")
async def process_docx(
    file: UploadFile = File(...),
    user_text: str = Form(...),
    ollama_url: str = Form("http://localhost:11434"),
    text_model: str = Form("qwen3:8b"),
    vision_model: str = Form("qwen2.5vl:3b"),
    use_ai: bool = Form(True),
    use_vision: bool = Form(True),
) -> dict[str, Any]:
    text_model = normalize_model_name(text_model, default="qwen3:8b")
    vision_model = normalize_model_name(vision_model, default="qwen2.5vl:3b")
    if vision_model == "qwen2.5vl:7b":
        vision_model = "qwen2.5vl:3b"
    ensure_ollama_ready(ollama_url, text_model, vision_model, use_ai, use_vision)

    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="DOCX 파일만 업로드할 수 있습니다.")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    upload_path = UPLOAD_DIR / safe_filename(file.filename)
    upload_path.write_bytes(await file.read())
    result = run_pipeline(
        template_path=upload_path,
        user_text=user_text,
        output_root=OUTPUT_DIR,
        text_model=text_model,
        vision_model=vision_model,
        ollama_url=ollama_url,
        use_ai=use_ai,
        use_vision=use_vision,
    )
    return public_result(result)


def normalize_model_name(value: str | None, default: str) -> str:
    value = (value or "").strip()
    return value or default


def ensure_ollama_ready(
    ollama_url: str,
    text_model: str,
    vision_model: str,
    use_ai: bool,
    use_vision: bool,
) -> None:
    required: list[str] = []
    if use_ai:
        required.append(text_model)
    if use_vision:
        required.append(vision_model)
    if not required:
        return

    models = list_models(ollama_url, timeout=3)
    if not models:
        raise HTTPException(
            status_code=503,
            detail=(
                "Ollama 서버에 연결할 수 없습니다. 새 PowerShell에서 "
                '`$env:OLLAMA_MODELS="D:\\OllamaModels"; ollama serve`를 먼저 실행하세요.'
            ),
        )

    missing = [model for model in required if model not in models]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Ollama에 필요한 모델이 없습니다: {', '.join(missing)}. 모델을 pull 한 뒤 다시 실행하세요.",
        )


@app.get("/api/file")
def download(path: str) -> FileResponse:
    target = Path(path).resolve()
    root = ROOT.resolve()
    if not str(target).lower().startswith(str(root).lower()) or not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    return FileResponse(target)


def public_result(result: dict[str, Any]) -> dict[str, Any]:
    def file_url(path: str | None) -> str | None:
        return f"/api/file?path={Path(path).resolve()}" if path else None

    return {
        **result,
        "final_docx_url": file_url(result.get("final_docx")),
        "final_pdf_url": file_url(result.get("final_pdf")),
        "preview_urls": [file_url(path) for path in result.get("preview_pngs", [])],
    }


FRONTEND_DIST = ROOT / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
