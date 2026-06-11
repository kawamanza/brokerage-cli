# brokerage

`brokerage` is a CLI for inspecting Brazilian brokerage note PDFs. It currently supports brokerage notes from **Clear** and **CM Capital**, including encrypted PDFs, multi-file batch processing, structured JSON/YAML output, and a human-readable summary view.

## Installation

This project uses Pipenv and pinned dependency versions.

```bash
pipenv sync --dev
pipenv run brokerage --help
```

## Usage

Inspect a single PDF:

```bash
pipenv run brokerage path/to/note.pdf --password "$PDF_PASSWORD"
```

Inspect a directory of PDFs:

```bash
pipenv run brokerage batch path/to/local-evaluation-folder --password "$PDF_PASSWORD"
```

Emit YAML instead of JSON:

```bash
pipenv run brokerage path/to/note.pdf --password "$PDF_PASSWORD" --output yaml
```

Print a human-readable summary:

```bash
pipenv run brokerage path/to/note.pdf --password "$PDF_PASSWORD" --summary
pipenv run brokerage batch path/to/local-evaluation-folder --password "$PDF_PASSWORD" --summary
```

## Password Handling

The CLI first tries to open a PDF without a password. If the PDF is encrypted and the terminal is interactive, it prompts:

```text
Enter the file password:
```

For `batch`, the prompt includes the file being opened:

```text
Enter the password for path/to/file.pdf:
```

Passwords are kept only in memory during the process. In non-interactive runs, encrypted PDFs require `--password`.

## Clear Parser Capabilities

The Clear parser currently extracts and organizes:

- source PDF metadata, including page count and whether a password was used;
- broker metadata available in the note text;
- customer metadata available in the note text;
- one or more negotiation notes inside the same PDF;
- one or more sheets/pages for the same negotiation note;
- note number, sheet number, trade date, settlement date, note type, and PDF pages used by each note;
- operations grouped under the correct negotiation note, including multiple operations on the same sheet;
- operation fields such as negotiation venue, side, market, term, title, asset, observation, quantity, price, total, debit/credit, and option strike when available;
- business summary values from the note;
- financial summary values, including IRRF, settlement fee, emoluments, operational fee, registration fee, and related totals.

Supported operation patterns include spot/fractional trades, ETFs, options, and option exercise rows observed in Clear note layouts.

## CM Capital Parser Capabilities

The CM Capital parser currently extracts and organizes:

- source PDF metadata, including page count and whether a password was used;
- broker metadata available in the note text;
- customer metadata available in the note text;
- one or more negotiation notes inside the same PDF;
- one or more sheets/pages for the same negotiation note;
- note number, sheet number, trade date, settlement date, note type, and PDF pages used by each note;
- option operation rows with fields such as negotiation venue, side, market, term, title, asset, observation, quantity, price, total, debit/credit, and strike when available;
- business summary values from the note;
- financial summary values, including IRRF, settlement fee, emoluments, operational fee, registration fee, net operations value, and net settlement.

Supported operation patterns currently include option buy/sell rows observed in CM Capital B3 note layouts. Additional market layouts should be added as broker-specific parser extensions.

## Output Modes

By default, output is compact JSON. Empty fields, nulls, empty collections, and zero-valued fields are omitted.

Use `--verbose` to preserve the full parsed model:

```bash
pipenv run brokerage path/to/note.pdf --password "$PDF_PASSWORD" --verbose
```

Use `--summary` for a readable text report. The summary:

- groups records by negotiation note first;
- keeps all sheets/pages from the same negotiation note together;
- aggregates operations by asset within each note;
- displays totals as `<asset> | $<sum_total> / <sum_quantity> = $<avg_price>`;
- includes operation count, side, market, debit/credit, allocated costs, and option strike when parsed;
- shows note-level financial fields;
- allocates settlement fee, emoluments, operational fee, and registration fee proportionally by each asset's traded total;
- assigns any rounding remainder to the asset with the largest traded total;
- separates files in `batch --summary` with a 40-character divider.

## Development Notes

Local folders such as `notes/` or `notas/` are evaluation-only inputs and are ignored by version control. Versioned test fixtures must use synthetic data under `tests/fixtures/`.

Run the test suite with:

```bash
pipenv run pytest
```
