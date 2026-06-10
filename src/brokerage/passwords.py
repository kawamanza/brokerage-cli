from __future__ import annotations

import sys
from getpass import getpass

from brokerage.errors import PdfPasswordRequiredError
from brokerage.models import ExtractedPdf
from brokerage.pdf import extract_pdf_text


class PasswordManager:
    def __init__(self, initial_password: str | None = None) -> None:
        self._passwords: list[str] = []
        if initial_password:
            self._passwords.append(initial_password)

    def extract(
        self,
        path,
        *,
        interactive: bool | None = None,
        prompt_context: str | None = None,
    ) -> ExtractedPdf:
        if interactive is None:
            interactive = sys.stdin.isatty()

        try:
            return extract_pdf_text(path)
        except PdfPasswordRequiredError:
            pass

        last_error: Exception | None = None
        for password in self._passwords:
            try:
                return extract_pdf_text(path, password)
            except PdfPasswordRequiredError as exc:
                last_error = exc
            except Exception as exc:
                last_error = exc

        if not interactive:
            raise PdfPasswordRequiredError(
                "PDF requires a password. Provide --password when running non-interactively."
            ) from last_error

        while True:
            password = getpass(_password_prompt(prompt_context))
            if not password:
                raise PdfPasswordRequiredError("No password provided.")

            try:
                extracted = extract_pdf_text(path, password)
            except Exception as exc:
                last_error = exc
                continue

            self._passwords.append(password)
            return extracted


def _password_prompt(context: str | None = None) -> str:
    if context:
        return f"Enter the password for {context}: "
    return "Enter the file password: "
