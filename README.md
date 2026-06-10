# brokerage

CLI for inspecting Brazilian brokerage note PDFs, with support for encrypted files and structured JSON/YAML output.

## Usage

```bash
brokerage path/to/note.pdf --password "$PDF_PASSWORD"
brokerage batch path/to/local-evaluation-folder --password "$PDF_PASSWORD" --output yaml
brokerage path/to/note.pdf --password "$PDF_PASSWORD" --summary
```

If an encrypted PDF requires a password and the terminal is interactive, the CLI prompts:

```text
Enter the file password:
```

`--summary` prints a human-readable summary grouped by negotiation note and asset. In non-interactive runs, encrypted PDFs require `--password`. Local folders such as `notes/` or `notas/` are evaluation-only inputs and are ignored by version control. Versioned test fixtures must use synthetic data under `tests/fixtures/`.
