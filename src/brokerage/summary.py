from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from brokerage.models import BatchResult, BrokerageFile, NegotiationNote, Operation


Money = Decimal
_TITLE_SUFFIX_MARKERS = {"ON", "PN", "UNT", "CI", "NM", "N1", "N2", "MA", "MB", "@", "#"}
_FINANCIAL_FIELDS = ("irrf", "settlement_fee", "emoluments", "operational_fee", "registration_fee")
_ALLOCATED_COST_FIELDS = ("settlement_fee", "emoluments", "operational_fee", "registration_fee")
_CENTS = Decimal("0.01")
_BATCH_SEPARATOR = "-" * 40


def summarize_payload(payload: BrokerageFile | BatchResult) -> str:
    if isinstance(payload, BatchResult):
        return summarize_batch(payload)
    return summarize_file(payload)


def summarize_batch(result: BatchResult) -> str:
    sections = [summarize_file(parsed_file) for parsed_file in result.results]
    if result.errors:
        lines = ["Errors:"]
        for error in result.errors:
            lines.append(f"- {error.get('source_file', '<unknown>')}: {error.get('error', '<unknown error>')}")
        sections.append("\n".join(lines))
    return f"\n\n{_BATCH_SEPARATOR}\n".join(section for section in sections if section)


def summarize_file(parsed_file: BrokerageFile) -> str:
    lines = [
        f'File: "{parsed_file.source_file}"',
        f"Broker: {parsed_file.broker.name}",
        f"Pages: {parsed_file.pages} | Notes: {len(parsed_file.notes)} | Operations: {sum(len(note.operations) for note in parsed_file.notes)}",
    ]

    for note in parsed_file.notes:
        lines.extend(["", *summarize_note(note)])
    return "\n".join(lines)


def summarize_note(note: NegotiationNote) -> list[str]:
    pages = ", ".join(str(page) for page in note.pdf_pages) or "unknown"
    header_parts = [f"Note {note.number or '<unknown>'}", f"type={note.broker_note_type.value}"]
    if note.trade_date:
        header_parts.append(f"trade_date={note.trade_date}")
    if note.settlement_date:
        header_parts.append(f"settlement_date={note.settlement_date}")
    header_parts.append(f"sheets={note.sheet_count}")
    header_parts.append(f"pages={pages}")

    lines = [" | ".join(header_parts), f"  Financial: {_financial_summary_text(note)}"]
    for summary in _asset_summaries(note):
        lines.append(f"  - {summary}")
    if not note.operations:
        lines.append("  - No operations parsed")
    return lines


def _financial_summary_text(note: NegotiationNote) -> str:
    parts = [f"{field}={format_money(_financial_value(note, field))}" for field in _FINANCIAL_FIELDS]
    parts.append(f"allocated_costs={format_money(_allocated_cost_total(note))}")
    return " | ".join(parts)


def _asset_summaries(note: NegotiationNote) -> list[str]:
    grouped = _group_operations_by_asset(note.operations)
    allocations = _allocated_costs_by_asset(grouped, _allocated_cost_total(note))

    summaries = []
    for asset in sorted(grouped):
        asset_operations = grouped[asset]
        total = _sum_decimal(operation.total for operation in asset_operations)
        quantity = _sum_decimal(operation.quantity for operation in asset_operations)
        average_price = total / quantity if quantity else Decimal("0")
        side = _same_or_mixed(operation.side for operation in asset_operations)
        market = _same_or_mixed(operation.market for operation in asset_operations)
        dc = _same_or_mixed(operation.debit_credit for operation in asset_operations)
        strike = _strike_summary(asset_operations)
        strike_text = f", strike={strike}" if strike else ""
        summaries.append(
            f"{asset} | {format_money(total)} / {format_decimal(quantity)} = {format_money(average_price)} "
            f"({len(asset_operations)} operations, side={side}, market=\"{market}\", dc={dc}, "
            f"allocated_costs={format_money(allocations.get(asset, Decimal('0')))}{strike_text})"
        )
    return summaries


def _group_operations_by_asset(operations: list[Operation]) -> dict[str, list[Operation]]:
    grouped: dict[str, list[Operation]] = defaultdict(list)
    for operation in operations:
        grouped[_asset_label(operation)].append(operation)
    return grouped


def _allocated_cost_total(note: NegotiationNote) -> Decimal:
    return _sum_decimal(_financial_value(note, field) for field in _ALLOCATED_COST_FIELDS)


def _allocated_costs_by_asset(grouped: dict[str, list[Operation]], cost_total: Decimal) -> dict[str, Decimal]:
    if not grouped or cost_total == 0:
        return {asset: Decimal("0") for asset in grouped}

    traded_totals = {
        asset: _sum_decimal(operation.total for operation in operations)
        for asset, operations in grouped.items()
    }
    traded_total = _sum_decimal(traded_totals.values())
    if traded_total == 0:
        return {asset: Decimal("0") for asset in grouped}

    allocations = {
        asset: ((cost_total * total) / traded_total).quantize(_CENTS, rounding=ROUND_HALF_UP)
        for asset, total in traded_totals.items()
    }
    remainder = cost_total.quantize(_CENTS, rounding=ROUND_HALF_UP) - _sum_decimal(allocations.values())
    if remainder:
        largest_asset = max(traded_totals, key=lambda asset: (traded_totals[asset], asset))
        allocations[largest_asset] += remainder
    return allocations


def _financial_value(note: NegotiationNote, field: str) -> Decimal:
    value = note.financial_summary.get(field)
    return value if isinstance(value, Decimal) else Decimal("0")


def _asset_label(operation: Operation) -> str:
    if _looks_like_option_code(operation.asset):
        return operation.asset or "<unknown>"
    title_label = _title_label(operation.title)
    return title_label or operation.asset or "<unknown>"


def _title_label(title: str | None) -> str | None:
    if not title:
        return None
    tokens = title.split()
    while tokens and (tokens[-1] in _TITLE_SUFFIX_MARKERS or _is_option_reference_token(tokens[-1])):
        tokens.pop()
    while tokens and tokens[-1] in _TITLE_SUFFIX_MARKERS:
        tokens.pop()
    return " ".join(tokens) if tokens else None


def _looks_like_option_code(asset: str | None) -> bool:
    return bool(asset and any(char.isdigit() for char in asset))


def _is_option_reference_token(value: str) -> bool:
    return any(char.isdigit() for char in value) or value.endswith("E")


def _sum_decimal(values) -> Decimal:
    total = Decimal("0")
    for value in values:
        if value is not None:
            total += value
    return total


def _strike_summary(operations: list[Operation]) -> str | None:
    strikes = {operation.strike for operation in operations if operation.strike is not None}
    if not strikes:
        return None
    if len(strikes) == 1:
        return format_money(next(iter(strikes)))
    return "mixed"


def _same_or_mixed(values) -> str:
    clean_values = {value for value in values if value}
    if not clean_values:
        return "unknown"
    if len(clean_values) == 1:
        return next(iter(clean_values))
    return "mixed"


def format_money(value: Decimal) -> str:
    return f"${format_decimal(value, places=2, trim=False)}"


def format_decimal(value: Decimal, *, places: int = 2, trim: bool = True) -> str:
    quantizer = Decimal("1") if places == 0 else Decimal("1").scaleb(-places)
    rounded = value.quantize(quantizer, rounding=ROUND_HALF_UP)
    text = f"{rounded:f}"
    if trim and "." in text:
        text = text.rstrip("0").rstrip(".")
    return text
