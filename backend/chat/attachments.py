"""Extracción de texto de adjuntos (PDF, Word, Excel, PowerPoint, TXT) e imágenes. Todo en memoria, con límites."""
import base64
import io
import xml.etree.ElementTree as ET
import zipfile

from docx import Document
from openpyxl import load_workbook
from pypdf import PdfReader

MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_CONTEXT_CHARS = 40_000   # tope de texto que llega al System Prompt
MAX_XLSX_ROWS = 2000
MAX_PDF_PAGES = 300
# Word y Excel son ZIP: un archivo de 1 MB puede descomprimirse en varios GB ("zip bomb") y tumbar el servidor.
MAX_UNZIPPED_BYTES = 80 * 1024 * 1024
MAX_ZIP_ENTRIES = 2000


class AttachmentError(ValueError):
    pass


def _check_zip(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
    except zipfile.BadZipFile as exc:
        raise AttachmentError("El archivo no es un documento de Office válido.") from exc
    if len(infos) > MAX_ZIP_ENTRIES or sum(i.file_size for i in infos) > MAX_UNZIPPED_BYTES:
        raise AttachmentError("El documento es demasiado grande para procesarlo.")


def _pdf_text(data: bytes) -> str:
    out, total = [], 0
    reader = PdfReader(io.BytesIO(data))
    for i, page in enumerate(reader.pages):
        if i >= MAX_PDF_PAGES:
            break
        text = page.extract_text() or ""
        out.append(text)
        total += len(text)
        if total >= MAX_CONTEXT_CHARS:  # no leer páginas que nunca se usarán
            break
    return "\n".join(out)


def _docx_text(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(c.text for c in row.cells))
    return "\n".join(parts)


def _xlsx_text(data: bytes) -> str:
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        lines = []
        for ws in wb.worksheets:
            lines.append(f"# Hoja: {ws.title}")
            for row in ws.iter_rows(values_only=True):
                if any(c is not None for c in row):
                    lines.append(" | ".join("" if c is None else str(c) for c in row))
                if len(lines) > MAX_XLSX_ROWS:
                    break
        return "\n".join(lines)
    finally:
        wb.close()


def _pptx_text(data: bytes) -> str:
    slides_text = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        slide_files = sorted(
            [n for n in zf.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")],
            key=lambda x: int("".join(filter(str.isdigit, x)) or 0)
        )
        for i, slide_name in enumerate(slide_files, start=1):
            try:
                root = ET.fromstring(zf.read(slide_name))
                slide_paragraphs = []
                for p in root.iter():
                    if p.tag.endswith("}p"):
                        p_text = "".join(t.text for t in p.iter() if t.tag.endswith("}t") and t.text).strip()
                        if p_text:
                            slide_paragraphs.append(p_text)
                if slide_paragraphs:
                    slides_text.append(f"--- Diapositiva {i} ---\n" + "\n".join(slide_paragraphs))
            except Exception:
                continue
    return "\n\n".join(slides_text)


def extract_attachment(name: str, data: bytes) -> dict:
    """Devuelve {'kind': 'text', 'text': ...} o {'kind': 'image', 'media_type', 'data'}."""
    if len(data) > MAX_FILE_BYTES:
        raise AttachmentError("El archivo supera los 8 MB.")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""

    if ext in {"png", "jpg", "jpeg"}:
        if len(data) > MAX_IMAGE_BYTES:
            raise AttachmentError("La imagen supera los 5 MB.")
        if data.startswith(b"\x89PNG"):
            media = "image/png"
        elif data.startswith(b"\xff\xd8"):
            media = "image/jpeg"
        else:
            raise AttachmentError("La imagen no es un PNG o JPG válido.")
        return {"kind": "image", "media_type": media, "data": base64.b64encode(data).decode()}

    readers = {
        "pdf": _pdf_text,
        "docx": _docx_text,
        "xlsx": _xlsx_text,
        "pptx": _pptx_text,
        "txt": lambda b: b.decode("utf-8", errors="replace"),
    }
    if ext not in readers:
        raise AttachmentError("Formato no admitido. Usa PDF, Word, Excel, PowerPoint, TXT, PNG o JPG.")

    if ext == "pdf" and not data.startswith(b"%PDF"):
        raise AttachmentError("El archivo no es un PDF válido.")
    if ext in {"docx", "xlsx", "pptx"}:
        if not data.startswith(b"PK"):
            raise AttachmentError("El archivo no es un documento de Office válido.")
        _check_zip(data)

    try:
        text = readers[ext](data)
    except Exception as exc:  # archivo corrupto, protegido con clave, etc.
        raise AttachmentError("No pude leer el archivo. Revisa que no esté dañado o protegido.") from exc

    text = text.strip()
    if not text:
        raise AttachmentError("El archivo no tiene texto legible.")
    return {"kind": "text", "text": text[:MAX_CONTEXT_CHARS]}
