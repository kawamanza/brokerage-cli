# brokerage

`brokerage` is a CLI for inspecting Brazilian brokerage note PDFs. It currently supports brokerage notes from **Clear**, **CM Capital**, **Ion Itaú**, **Nu Investimentos**, and the generic **SINACOR** B3 note model, including encrypted PDFs, multi-file batch processing, structured JSON/YAML output, and a human-readable summary view.

## Intended Use

This project is selfware: it was built to solve a personal workflow for standardizing the reading of brokerage notes for personal investment control.

Its main goals are:

- reading brokerage note PDFs into a consistent local structure;
- helping reconcile personal investment records;
- supporting average-price tracking;
- allocating note-level fees and costs across assets from the same note, to support more accurate personal average-price adjustments.

This CLI is not official software from any brokerage, exchange, tax authority, regulator, or financial institution. It is not tax, accounting, investment, legal, or financial advice.

Use extra care before relying on this project in official, regulated, professional, or commercial contexts. Parser output is best-effort and must be checked against the original brokerage note and any applicable official records before being used in tax filings, accounting books, investment decisions, customer-facing services, or paid products.

Commercial use, hosted services, official tax/accounting/financial products, resale, sublicensing, or professional advisory workflows require prior permission under the project license.

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

## Ion Itaú Parser Capabilities

The Ion Itaú parser currently extracts and organizes:

- source PDF metadata, including page count and whether a password was used;
- broker metadata available in the note text, identifying the broker as `Ion Itaú` and preserving the legal name when present;
- customer metadata available in the note text;
- one or more negotiation notes inside the same PDF;
- one or more sheets/pages for the same negotiation note;
- note number, sheet number, trade date, settlement date, note type, and PDF pages used by each note;
- fractional and spot stock operation rows with fields such as negotiation venue, side, market, title, asset, observation, quantity, price, total, and debit/credit;
- business summary values from the note;
- financial summary values, including settlement fee, emoluments, registration fee, net operations value, and net settlement.

Supported operation patterns currently include complete `B3 RV LISTADO` stock rows from the Ion Itaú B3 brokerage-note layout. Additional Ion Itaú markets should be added as broker-specific parser extensions.

## Nu Investimentos Parser Capabilities

The Nu Investimentos parser currently extracts and organizes:

- source PDF metadata, broker metadata, and customer metadata available in the note text;
- one or more negotiation notes and sheets/pages grouped by note number;
- note number, sheet number, trade date, settlement date, note type, and PDF pages used by each note;
- own-layout `BOVESPA` spot operation rows with title, asset, observation, quantity, price, total, side, and debit/credit;
- business summary values and financial summary values, including settlement fee, emoluments, registration fee, IRRF, net operations value, and net settlement.

Supported operation patterns currently include complete spot rows observed in the Nu Investimentos/Nubank Investimentos proprietary note layout.

## SINACOR Parser Capabilities

The SINACOR parser currently extracts and organizes:

- source PDF metadata and the broker legal name from the SINACOR/B3 note header;
- `broker.name` as `SINACOR`, with `broker.legal_name` preserving the institution that issued the note;
- customer metadata available in the note text;
- one or more negotiation notes and sheets/pages grouped by note number;
- complete `B3 RV LISTADO` spot operation rows with title, asset, observation, quantity, price, total, side, and debit/credit;
- business summary values and financial summary values, including settlement fee, emoluments, registration fee, net operations value, and net settlement.

For `--summary`, SINACOR files render the broker line as `Broker: SINACOR (<legal_name>)`. The parser is generic for the SINACOR model, with initial coverage validated against a Nu Investimentos sample.

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
- allocates settlement fee, emoluments, operational fee, registration fee, and transfer fee proportionally by each asset's traded total;
- assigns any rounding remainder to the asset with the largest traded total;
- separates files in `batch --summary` with a 40-character divider.

## License

This project is distributed under the [Brokerage CLI Selfware Non-Commercial License](LICENSE.md).

In short: personal, educational, research, and internal non-commercial use are allowed; commercial use and official/professional financial, tax, accounting, or advisory use require prior written permission. The license also disclaims warranties and responsibility for parser accuracy, financial losses, tax penalties, or regulatory suitability.

## Development Notes

Local folders such as `notes/` or `notas/` are evaluation-only inputs and are ignored by version control. Versioned test fixtures must use synthetic data under `tests/fixtures/`.

Run the test suite with:

```bash
pipenv run pytest
```
