import io

import pytest

from src.ingest.extract_text import UnsupportedFileError, extract_text


def test_plain_text_and_markdown_are_read() -> None:
    assert extract_text("notes.txt", b"We need identity checks.\r\n") == "We need identity checks."
    assert extract_text("notes.md", "# Title\nBody".encode()) == "# Title\nBody"


def test_eml_includes_headers_and_body() -> None:
    raw = b"From: Arjun <a@bank.in>\nTo: team@bank.in\nSubject: KYC points\n\nWe must keep records for five years."
    text = extract_text("mail.eml", raw)
    assert "Subject: KYC points" in text and "five years" in text


def test_docx_paragraphs_and_tables_are_read() -> None:
    import docx

    document = docx.Document()
    document.add_paragraph("The bank must screen customers against sanctions lists.")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Retention"
    table.rows[0].cells[1].text = "5 years"
    buffer = io.BytesIO()
    document.save(buffer)

    text = extract_text("req.docx", buffer.getvalue())
    assert "sanctions lists" in text and "Retention | 5 years" in text


def test_unsupported_empty_and_oversized_files_are_rejected() -> None:
    with pytest.raises(UnsupportedFileError):
        extract_text("tool.exe", b"MZ")
    with pytest.raises(UnsupportedFileError):
        extract_text("empty.txt", b"   \n  ")
    with pytest.raises(UnsupportedFileError):
        extract_text("big.txt", b"x" * (9 * 1024 * 1024))
