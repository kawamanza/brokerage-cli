---
name: brokerage-cli
description: Use when working on this project's brokerage note inspection CLI, including PDF parsing, password handling, output schema changes, broker/layout parser evolution, CLI options, tests, and dependency management.
---

# Brokerage CLI

Use this skill when modifying the brokerage note inspection utility in this repository.

## Project Shape

- Python package lives in `src/brokerage`.
- Console command is `brokerage`, wired in `pyproject.toml` as `brokerage.cli:main`.
- The package uses a `src/` layout and tests live in `tests/`.
- Runtime and dev dependencies must be pinned with exact versions (`==...`) in project manifests. Do not introduce open ranges like `>=...` or `*` for installable dependencies.
- Keep parser code broker/layout-specific under `src/brokerage/brokers/`, with shared orchestration in `parser.py`, PDF extraction in `pdf.py`, CLI wiring in `cli.py`, and output models in `models.py`.

## CLI Behavior

- Default single-file usage is `brokerage FILE --password ...`; internally `main()` routes this to the inspection command.
- Keep `brokerage inspect FILE` available as an explicit equivalent unless the user asks to remove it.
- Batch usage is `brokerage batch PATH --password ...`.
- Supported output formats are controlled by `--output`, currently `json` and `yaml`.
- Output is compact by default: omit nulls, empty strings, empty lists/dicts, and zero-valued fields such as `0`, `0.0`, and `"0.00"`.
- `--verbose` must preserve the full model output, including nulls, empty collections, warnings, and zero-valued fields.
- `--summary` prints a human-readable text summary instead of structured JSON/YAML. It must group records by negotiation note first, then aggregate operations by asset within each note. Include note-level financial fields (`irrf`, `settlement_fee`, `emoluments`, `operational_fee`, `registration_fee`) and allocate `settlement_fee + emoluments + operational_fee + registration_fee` proportionally by asset traded total, with cent rounding remainders assigned to the largest asset total. When option operations have a parsed strike, show it after `allocated_costs`.

## Password Handling

- PDFs may be encrypted. First try opening without a password.
- If a password is required and `--password` was provided, try it.
- In interactive terminals, prompt with `Enter the file password: ` for single-file inspection, and include the file path in batch prompts as `Enter the password for <path>: `.
- In batch mode, keep valid entered passwords in memory and retry them against later files.
- Never persist passwords, print passwords, add passwords to fixtures, or include real passwords in docs, tests, skills, logs, or examples.
- In non-interactive mode, fail with a user-facing error if an encrypted PDF cannot be opened and no valid password was supplied.

## Domain Model

The top-level parse result represents a source PDF file, not a single brokerage note.

- `BrokerageFile`: source file metadata, broker info, customer info, PDF page count, password usage, parsed notes, computed counts, warnings.
- `NegotiationNote`: one negotiation note identified inside the PDF. A single PDF can contain many notes.
- `Sheet`: one physical/visual note sheet, usually tied to a PDF page. A single negotiation note can span multiple sheets.
- `Operation`: one trade row extracted from a note table.

Important invariants:

- Group sheets by the note identifier from the PDF content, not by PDF page number.
- A two-page PDF can be either two separate notes or one note with two sheets; parse and aggregate accordingly.
- `sheet_count` is the number of grouped sheets for a note.
- `pdf_pages` records which PDF pages contributed to a note.
- Note-level `operations`, `business_summary`, and `financial_summary` aggregate values from all grouped sheets.
- Preserve per-sheet detail under `notes[].sheets[]` for auditability.
- Human summaries must keep operations from the same negotiation note together even when the note spans multiple PDF pages/sheets.

## Parsing Approach

- Extract page-level text and preserve both full text and `page_texts`; page-level text is required for sheet grouping.
- Parsers should detect:
  - broker/institution identity,
  - note type, such as stocks, ETFs, real estate funds, options, mixed, or unknown,
  - layout version,
  - note number,
  - sheet number,
  - trade date and settlement date,
  - customer and broker metadata,
  - operations, including option strike when option observation starts with a monetary number,
  - business and financial summaries.
- Prefer parser logic that is tolerant of missing fields and records warnings instead of crashing, unless the file cannot be opened or the broker/layout cannot be identified.
- Do not hard-code behavior from one sample as a universal rule. Treat every broker and layout version as an extension point.
- Keep raw extracted operation text in `Operation.raw` so future parser fixes can be audited.

## Privacy Rules

- Do not expose real names, documents, addresses, phone numbers, account codes, passwords, or source note values in skills, docs, committed fixtures, examples, or comments.
- Local folders such as `notes/` or `notas/` are evaluation-only inputs and must stay out of version control.
- Versioned fixtures belong under `tests/fixtures/` and must use synthetic/fake data only.
- Tests should use synthetic text fixtures unless the user explicitly asks for tests against local sample files.
- If using a real local PDF for manual validation, summarize behavior and do not copy sensitive fields into project documentation.

## Testing And Validation

For behavior changes, run:

```bash
pipenv run pytest
```

When CLI behavior changes, also validate at least:

```bash
pipenv run brokerage --help
pipenv run brokerage <sample-pdf> --password <password>
pipenv run brokerage batch <sample-dir> --password <password>
```

Use placeholder values in docs and examples. Do not commit real passwords or sensitive output.
