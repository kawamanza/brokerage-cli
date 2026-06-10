from __future__ import annotations

from pathlib import Path
import sys
from typing import Annotated

import typer
from rich.console import Console

from brokerage.errors import BrokerageInspectError
from brokerage.models import BatchResult, OutputFormat
from brokerage.parser import parse_note
from brokerage.passwords import PasswordManager
from brokerage.serializers import serialize_payload
from brokerage.summary import summarize_payload


app = typer.Typer(help="Inspect Brazilian brokerage note PDFs.")
console = Console()
err_console = Console(stderr=True)


PasswordOption = Annotated[
    str | None,
    typer.Option("--password", "-p", help="Password for encrypted PDF files."),
]
OutputOption = Annotated[
    OutputFormat,
    typer.Option("--output", "-o", help="Output format."),
]
VerboseOption = Annotated[
    bool,
    typer.Option("--verbose", "-v", help="Include empty and zero-valued fields in the output."),
]
SummaryOption = Annotated[
    bool,
    typer.Option("--summary", help="Print a human-readable summary instead of structured output."),
]


@app.command()
def inspect(
    file: Annotated[Path, typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True)],
    password: PasswordOption = None,
    output: OutputOption = OutputFormat.JSON,
    verbose: VerboseOption = False,
    summary: SummaryOption = False,
) -> None:
    """Inspect a single brokerage note PDF."""
    manager = PasswordManager(password)
    try:
        extracted = manager.extract(file)
        note = parse_note(extracted)
    except BrokerageInspectError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if summary:
        console.print(summarize_payload(note))
    else:
        console.print(serialize_payload(note, output, compact=not verbose))


@app.command()
def batch(
    path: Annotated[Path, typer.Argument(exists=True, file_okay=True, dir_okay=True, readable=True)],
    password: PasswordOption = None,
    output: OutputOption = OutputFormat.JSON,
    verbose: VerboseOption = False,
    summary: SummaryOption = False,
) -> None:
    """Inspect every PDF under a file or directory path."""
    manager = PasswordManager(password)
    result = BatchResult()

    for pdf_path in _pdf_paths(path):
        try:
            extracted = manager.extract(pdf_path, prompt_context=str(pdf_path))
            result.results.append(parse_note(extracted))
        except BrokerageInspectError as exc:
            result.errors.append({"source_file": str(pdf_path), "error": str(exc)})

    if summary:
        console.print(summarize_payload(result))
    else:
        console.print(serialize_payload(result, output, compact=not verbose))


def _pdf_paths(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(item for item in path.rglob("*.pdf") if item.is_file())


def main() -> None:
    known_commands = {"batch", "inspect"}
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-") and sys.argv[1] not in known_commands:
        sys.argv.insert(1, "inspect")
    app()


if __name__ == "__main__":
    main()
