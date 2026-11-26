"""Turns an uploaded file into plain text. Supports .txt .md .csv .json .eml .docx .pdf."""

from __future__ import annotations

import email
import io
from email import policy
from pathlib import PurePath

MAX_BYTES = 8 * 1024 * 1024
MAX_CHARS = 200_000

TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".csv", ".json", ".log", ".rtf", ""}


class UnsupportedFileError(ValueError):
    pass


def extract_text(filename: str, data: bytes) -> str:
    """Returns the text content of an uploaded file, or raises UnsupportedFileError."""
    if len(data) > MAX_BYTES:
        raise UnsupportedFileError(f"{filename} is larger than {MAX_BYTES // (1024 * 1024)} MB")

    suffix = PurePath(filename).suffix.lower()
    if suffix == ".docx":
        text = _docx(data)
    elif suffix == ".pdf":
        text = _pdf(data)
    elif suffix == ".eml":
        text = _eml(data)
    elif suffix in TEXT_SUFFIXES:
        text = data.decode("utf-8", errors="replace")
    else:
        raise UnsupportedFileError(f"Unsupported file type '{suffix}'. Use .txt .md .eml .docx or .pdf")

    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise UnsupportedFileError(f"{filename} contains no readable text")
    return text[:MAX_CHARS]


def _docx(data: bytes) -> str:
    import docx  # python-docx

    document = docx.Document(io.BytesIO(data))
    parts = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join((page.extract_text() or "").strip() for page in reader.pages)


def _eml(data: bytes) -> str:
    message = email.message_from_bytes(data, policy=policy.default)
    header = "\n".join(
        f"{name}: {message[name]}" for name in ("From", "To", "Date", "Subject") if message[name]
    )
    body = message.get_body(preferencelist=("plain", "html"))
    content = body.get_content() if body is not None else ""
    return f"{header}\n\n{content}".strip()
