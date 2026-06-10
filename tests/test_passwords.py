from pathlib import Path

import pytest

from brokerage.errors import PdfInvalidPasswordError, PdfPasswordRequiredError
from brokerage.models import ExtractedPdf
from brokerage.passwords import PasswordManager, _password_prompt


def test_password_manager_reuses_initial_password(monkeypatch):
    calls = []

    def fake_extract(path, password=None):
        calls.append((path, password))
        if password != "secret":
            raise PdfPasswordRequiredError("password required")
        return ExtractedPdf(source_file=path, text="CLEAR", pages=1, used_password=True)

    monkeypatch.setattr("brokerage.passwords.extract_pdf_text", fake_extract)

    manager = PasswordManager("secret")
    first = manager.extract(Path("a.pdf"), interactive=False)
    second = manager.extract(Path("b.pdf"), interactive=False)

    assert first.used_password is True
    assert second.used_password is True
    assert calls == [
        (Path("a.pdf"), None),
        (Path("a.pdf"), "secret"),
        (Path("b.pdf"), None),
        (Path("b.pdf"), "secret"),
    ]


def test_password_manager_fails_non_interactive_without_password(monkeypatch):
    def fake_extract(path, password=None):
        raise PdfPasswordRequiredError("password required")

    monkeypatch.setattr("brokerage.passwords.extract_pdf_text", fake_extract)

    manager = PasswordManager()

    with pytest.raises(PdfPasswordRequiredError):
        manager.extract(Path("a.pdf"), interactive=False)


def test_password_manager_prompts_until_valid_and_reuses_password(monkeypatch):
    attempts = []

    def fake_extract(path, password=None):
        attempts.append(password)
        if password == "right":
            return ExtractedPdf(source_file=path, text="CLEAR", pages=1, used_password=True)
        if password is None:
            raise PdfPasswordRequiredError("password required")
        raise PdfInvalidPasswordError("bad password")

    prompts = iter(["wrong", "right"])
    prompt_messages = []

    def fake_getpass(prompt):
        prompt_messages.append(prompt)
        return next(prompts)

    monkeypatch.setattr("brokerage.passwords.extract_pdf_text", fake_extract)
    monkeypatch.setattr("brokerage.passwords.getpass", fake_getpass)

    manager = PasswordManager()

    extracted = manager.extract(Path("a.pdf"), interactive=True)
    reused = manager.extract(Path("b.pdf"), interactive=False)

    assert extracted.used_password is True
    assert reused.used_password is True
    assert attempts == [None, "wrong", "right", None, "right"]
    assert prompt_messages == ["Enter the file password: ", "Enter the file password: "]


def test_password_prompt_can_include_file_context():
    assert _password_prompt() == "Enter the file password: "
    assert _password_prompt("notes/example.pdf") == "Enter the password for notes/example.pdf: "


def test_password_manager_prompt_uses_file_context(monkeypatch):
    def fake_extract(path, password=None):
        if password == "secret":
            return ExtractedPdf(source_file=path, text="CLEAR", pages=1, used_password=True)
        raise PdfPasswordRequiredError("password required")

    prompt_messages = []

    def fake_getpass(prompt):
        prompt_messages.append(prompt)
        return "secret"

    monkeypatch.setattr("brokerage.passwords.extract_pdf_text", fake_extract)
    monkeypatch.setattr("brokerage.passwords.getpass", fake_getpass)

    manager = PasswordManager()
    extracted = manager.extract(Path("notes/example.pdf"), interactive=True, prompt_context="notes/example.pdf")

    assert extracted.used_password is True
    assert prompt_messages == ["Enter the password for notes/example.pdf: "]
