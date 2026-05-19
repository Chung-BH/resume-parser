"""DOCX rendering utilities."""

from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any


def render_docx(docx_path: str | Path, out_dir: str | Path, prefix: str = "page") -> dict[str, Any]:
    output_dir = Path(out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []

    pdf_result = libreoffice_to_pdf(docx_path, output_dir)
    warnings.extend(pdf_result["warnings"])
    render_mode = pdf_result["mode"]
    pdf = pdf_result["pdf"]

    if not pdf:
        pdf_result = word_to_pdf(docx_path, output_dir)
        warnings.extend(pdf_result["warnings"])
        render_mode = pdf_result["mode"]
        pdf = pdf_result["pdf"]

    if not pdf:
        preview_result = structural_preview(docx_path, output_dir, prefix=prefix)
        warnings.extend(preview_result["warnings"])
        return {"pdf": None, "pngs": preview_result["pngs"], "page_sizes": preview_result["page_sizes"], "warnings": warnings, "mode": "structural"}

    png_result = pdf_to_pngs(pdf, output_dir, prefix=prefix)
    warnings.extend(png_result["warnings"])
    return {"pdf": pdf, "pngs": png_result["pngs"], "page_sizes": png_result["page_sizes"], "warnings": warnings, "mode": render_mode}


def word_to_pdf(docx_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    result: dict[str, Any] = {"pdf": None, "warnings": [], "mode": "word"}
    output_dir = Path(out_dir).resolve()
    safe_docx = output_dir / "_word_input.docx"
    output_pdf = output_dir / "rendered.pdf"
    shutil.copy2(docx_path, safe_docx)
    if output_pdf.exists():
        output_pdf.unlink()

    code = r"""
from pathlib import Path
import sys

docx = str(Path(sys.argv[1]).resolve())
pdf = str(Path(sys.argv[2]).resolve())
word = None
doc = None
try:
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    doc = word.Documents.Open(docx, ReadOnly=True, AddToRecentFiles=False)
    try:
        doc.ExportAsFixedFormat(pdf, 17)
    except Exception:
        doc.SaveAs(pdf, FileFormat=17)
    doc.Close(False)
    word.Quit()
    pythoncom.CoUninitialize()
except Exception as exc:
    try:
        if doc is not None:
            doc.Close(False)
    except Exception:
        pass
    try:
        if word is not None:
            word.Quit()
    except Exception:
        pass
    print(str(exc), file=sys.stderr)
    sys.exit(1)
"""
    command = [sys.executable, "-c", code, str(safe_docx), str(output_pdf)]
    try:
        completed = run_process(command, timeout=15)
    except subprocess.TimeoutExpired:
        result["warnings"].append("Microsoft Word conversion timed out")
        return result
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "Microsoft Word conversion failed").strip()
        result["warnings"].append(message)
        return result
    if output_pdf.exists():
        result["pdf"] = str(output_pdf)
    else:
        result["warnings"].append("Microsoft Word did not create PDF")
    return result


def libreoffice_to_pdf(docx_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    result: dict[str, Any] = {"pdf": None, "warnings": [], "mode": "libreoffice"}
    soffice = find_soffice()
    if not soffice:
        result["warnings"].append("LibreOffice not found")
        return result

    output_dir = Path(out_dir).resolve()
    profile_dir = tempfile.mkdtemp(prefix="lo-profile-", dir=output_dir)
    safe_docx = output_dir / "_input.docx"
    safe_pdf = output_dir / "_input.pdf"
    shutil.copy2(docx_path, safe_docx)
    command = [
        soffice,
        "--headless",
        "--norestore",
        "--nolockcheck",
        "--nodefault",
        "--nofirststartwizard",
        f"-env:UserInstallation={Path(profile_dir).resolve().as_uri()}",
        "--convert-to",
        "pdf",
        "--outdir",
        str(output_dir),
        str(safe_docx),
    ]
    try:
        completed = run_process(command, timeout=45)
        if completed.returncode != 0:
            result["warnings"].append((completed.stderr or completed.stdout or "LibreOffice failed").strip())
            return result
    except subprocess.TimeoutExpired:
        kill_office_processes()
        result["warnings"].append("LibreOffice conversion timed out")
        return result
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)

    output_pdf = output_dir / "rendered.pdf"
    if safe_pdf.exists():
        if output_pdf.exists():
            output_pdf.unlink()
        safe_pdf.replace(output_pdf)
    if output_pdf.exists():
        result["pdf"] = str(output_pdf)
    else:
        result["warnings"].append("LibreOffice did not create PDF")
    return result


def pdf_to_pngs(pdf_path: str | Path, out_dir: str | Path, prefix: str = "page") -> dict[str, Any]:
    result: dict[str, Any] = {"pngs": [], "page_sizes": [], "warnings": []}
    try:
        import fitz  # type: ignore
        try:
            fitz.TOOLS.mupdf_display_errors(False)
            fitz.TOOLS.mupdf_display_warnings(False)
        except Exception:
            pass
    except Exception:
        result["warnings"].append("PyMuPDF not available")
        return result

    doc = fitz.open(pdf_path)
    output_dir = Path(out_dir)
    for index, page in enumerate(doc, start=1):
        pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
        png = output_dir / f"{prefix}_{index}.png"
        pix.save(png)
        result["pngs"].append(str(png))
        result["page_sizes"].append(
            {
                "page": index,
                "pdf_width": float(page.rect.width),
                "pdf_height": float(page.rect.height),
                "png_width": float(pix.width),
                "png_height": float(pix.height),
            }
        )
    doc.close()
    return result


def structural_preview(docx_path: str | Path, out_dir: str | Path, prefix: str = "page") -> dict[str, Any]:
    result: dict[str, Any] = {"pngs": [], "page_sizes": [], "warnings": []}
    try:
        from docx import Document
        from PIL import Image, ImageDraw, ImageFont  # type: ignore
    except Exception:
        result["warnings"].append("Structural preview unavailable")
        return result

    document = Document(str(docx_path))
    tables = document.tables
    if not tables:
        result["warnings"].append("No DOCX table found for structural preview")
        return result

    width = 1400
    margin_x = 70
    y = 70
    max_cols = max((len(row.cells) for table in tables for row in table.rows), default=1)
    col_width = max(38, (width - margin_x * 2) // max(max_cols, 1))
    row_height = 44
    height = max(900, 160 + sum(len(table.rows) for table in tables) * row_height)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = load_font(ImageFont, 18)

    for table in tables:
        for row in table.rows:
            for cell_index, cell in enumerate(row.cells):
                x0 = margin_x + cell_index * col_width
                y0 = y
                x1 = x0 + col_width
                y1 = y + row_height
                text = " ".join(cell.text.split())
                fill = "#f4f4f4" if text else "white"
                draw.rectangle([x0, y0, x1, y1], outline="black", fill=fill, width=1)
                if text:
                    draw.text((x0 + 4, y0 + 10), text[:10], fill="black", font=font)
            y += row_height
        y += 24

    png = Path(out_dir) / f"{prefix}_structural_1.png"
    image.save(png)
    result["pngs"].append(str(png))
    result["page_sizes"].append({"page": 1, "png_width": width, "png_height": height})
    result["warnings"].append("Used structural preview because LibreOffice rendering failed")
    return result


def find_soffice() -> str | None:
    candidates = [
        shutil.which("soffice.com"),
        shutil.which("soffice"),
        r"C:\Program Files\LibreOffice\program\soffice.com",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def run_process(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    if os.name != "nt":
        return subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    started = time.monotonic()
    while process.poll() is None:
        if time.monotonic() - started > timeout:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], check=False, capture_output=True, text=True)
            stdout, stderr = process.communicate(timeout=5)
            raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr)
        time.sleep(0.5)
    stdout, stderr = process.communicate()
    return subprocess.CompletedProcess(command, process.returncode or 0, stdout, stderr)


def kill_office_processes() -> None:
    if os.name != "nt":
        return
    for name in ["soffice.exe", "soffice.bin", "soffice.com"]:
        subprocess.run(["taskkill", "/IM", name, "/F"], check=False, capture_output=True, text=True)


def load_font(image_font: Any, size: int) -> Any:
    for candidate in [r"C:\Windows\Fonts\malgun.ttf", r"C:\Windows\Fonts\gulim.ttc"]:
        if Path(candidate).exists():
            try:
                return image_font.truetype(candidate, size)
            except Exception:
                pass
    return image_font.load_default()
