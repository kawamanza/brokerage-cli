from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, PdfReadError, WrongPasswordError

from brokerage.errors import PdfInvalidPasswordError, PdfPasswordRequiredError
from brokerage.models import ExtractedPdf


def extract_pdf_text(path: Path, password: str | None = None) -> ExtractedPdf:
    try:
        reader = PdfReader(path)
    except PdfReadError as exc:
        raise PdfPasswordRequiredError(str(exc)) from exc

    used_password = False
    if reader.is_encrypted:
        if not password:
            raise PdfPasswordRequiredError("PDF requires a password.")

        try:
            decrypt_result = reader.decrypt(password)
        except (WrongPasswordError, PdfReadError) as exc:
            raise PdfInvalidPasswordError("Invalid PDF password.") from exc

        if decrypt_result == 0:
            raise PdfInvalidPasswordError("Invalid PDF password.")
        used_password = True

    try:
        page_text = [page.extract_text() or "" for page in reader.pages]
    except FileNotDecryptedError as exc:
        raise PdfInvalidPasswordError("Invalid PDF password.") from exc

    return ExtractedPdf(
        source_file=path,
        text="\n".join(page_text),
        pages=len(reader.pages),
        page_texts=page_text,
        used_password=used_password,
    )
