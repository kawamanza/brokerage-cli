from __future__ import annotations

import re
from collections import OrderedDict
from decimal import Decimal, InvalidOperation
from typing import Any

from brokerage.models import (
    BrokerInfo,
    BrokerageFile,
    BrokerNoteType,
    CustomerInfo,
    ExtractedPdf,
    NegotiationNote,
    Operation,
    Sheet,
)


class ClearParser:
    broker_name = "Clear"

    def matches(self, text: str) -> bool:
        normalized = text.upper()
        return "CLEAR" in normalized or "CLEAR CTVM" in normalized or "CLEAR CORRETORA" in normalized

    def parse(self, extracted: ExtractedPdf) -> BrokerageFile:
        page_texts = extracted.page_texts or extracted.text.split("\f") or [extracted.text]
        sheets = [self._parse_sheet(text, index) for index, text in enumerate(page_texts, start=1) if text.strip()]
        notes = self._group_notes(sheets)
        warnings: list[str] = []

        if not notes:
            warnings.append("No negotiation notes were parsed from the extracted text.")

        layout_version = self._layout_version(extracted.text)
        if layout_version == "unknown":
            warnings.append("Clear layout version could not be identified.")

        return BrokerageFile(
            broker=self._broker_info(extracted.text),
            layout_version=layout_version,
            source_file=str(extracted.source_file),
            pages=extracted.pages,
            used_password=extracted.used_password,
            customer=self._customer_info(extracted.text),
            notes=notes,
            computed={
                "note_count": len(notes),
                "sheet_count": sum(note.sheet_count for note in notes),
                "operation_count": sum(len(note.operations) for note in notes),
                "asset_count": len({asset for note in notes for asset in note.assets}),
            },
            warnings=warnings,
        )

    def _parse_sheet(self, text: str, pdf_page: int) -> tuple[dict[str, Any], Sheet]:
        lines = self._lines(text)
        note_number = self._value_after(lines, "Nr. nota")
        sheet_number = self._int_or_none(self._value_after(lines, "Folha"))
        trade_date = self._value_after(lines, "Data pregão")
        operations = self._operations(lines)
        financial_summary = self._financial_summary(lines)

        header = {
            "number": note_number,
            "trade_date": trade_date,
            "settlement_date": financial_summary.get("settlement_date"),
        }
        warnings: list[str] = []
        if not operations:
            warnings.append("No operations were parsed from this sheet.")

        return header, Sheet(
            pdf_page=pdf_page,
            sheet_number=sheet_number,
            operations=operations,
            business_summary=self._business_summary(lines),
            financial_summary=financial_summary,
            warnings=warnings,
        )

    def _group_notes(self, parsed_sheets: list[tuple[dict[str, Any], Sheet]]) -> list[NegotiationNote]:
        grouped: OrderedDict[str, dict[str, Any]] = OrderedDict()
        for index, (header, sheet) in enumerate(parsed_sheets, start=1):
            key = header.get("number") or f"unknown-{index}"
            if key not in grouped:
                grouped[key] = {"header": header, "sheets": []}
            grouped[key]["sheets"].append(sheet)

        notes: list[NegotiationNote] = []
        for group in grouped.values():
            header = group["header"]
            sheets: list[Sheet] = group["sheets"]
            operations = [operation for sheet in sheets for operation in sheet.operations]
            assets = sorted({operation.asset for operation in operations if operation.asset})
            business_summary = self._merge_dicts(sheet.business_summary for sheet in sheets)
            financial_summary = self._merge_dicts(sheet.financial_summary for sheet in sheets)
            warnings = [warning for sheet in sheets for warning in sheet.warnings]

            notes.append(
                NegotiationNote(
                    number=header.get("number"),
                    broker_note_type=self._note_type(operations),
                    trade_date=header.get("trade_date"),
                    settlement_date=header.get("settlement_date"),
                    sheet_count=len(sheets),
                    pdf_pages=[sheet.pdf_page for sheet in sheets],
                    assets=assets,
                    operations=operations,
                    sheets=sheets,
                    business_summary=business_summary,
                    financial_summary=financial_summary,
                    computed={
                        "operation_count": len(operations),
                        "asset_count": len(assets),
                    },
                    warnings=warnings,
                )
            )
        return notes

    def _broker_info(self, text: str) -> BrokerInfo:
        lines = self._lines(text)
        legal_name = self._first_line_matching(lines, r"CLEAR\s+CTVM")
        website = self._first_match(text, r"Internet:\s*(\S+)")
        sac = self._first_match(text, r"SAC:\s*([\d\-]+)")
        ombudsman = self._first_match(text, r"Ouvidoria:\s*(?:Tel\.\s*)?([\d\-]+)")
        return BrokerInfo(
            name=self.broker_name,
            legal_name=legal_name,
            document=self._first_match(text, r"C\.N\.P\.J:\s*([\d\./-]+)"),
            address=self._address_after(lines, legal_name),
            phones=re.findall(r"\+?\d{2}\s+\d{4}-\d{4}|\d{4}-\d{4}|\d{3,4}-\d{3,4}", text),
            website=website,
            customer_service_phone=sac,
            ombudsman_phone=ombudsman,
        )

    def _customer_info(self, text: str) -> CustomerInfo:
        lines = self._lines(text)
        customer_idx = self._index_of(lines, "Cliente")
        code = lines[customer_idx + 1] if customer_idx is not None and customer_idx + 1 < len(lines) else None
        name = lines[customer_idx + 2] if customer_idx is not None and customer_idx + 2 < len(lines) else None
        address = lines[customer_idx + 3] if customer_idx is not None and customer_idx + 3 < len(lines) else None
        phone = self._first_match(text, r"Tel\.\s*(\([^)]+\)\s*\d{4,5}-\d{4})")
        custodian_idx = self._index_of(lines, "Custodiante")
        custodian = lines[custodian_idx + 1] if custodian_idx is not None and custodian_idx + 1 < len(lines) else None
        if custodian in {"C.I", "Complemento nome"}:
            custodian = None
        return CustomerInfo(
            code=code,
            name=name,
            document=self._customer_document(lines),
            address=address,
            phone=phone,
            advisor_code=self._value_after(lines, "Assessor"),
            custodian=custodian,
            qualified_agent_settlement=self._yes_no_after(lines, "C.I"),
            related_person=self._yes_no_after(lines, "P. Vinc"),
        )

    def _operations(self, lines: list[str]) -> list[Operation]:
        try:
            start = lines.index("D/C") + 1
            end = lines.index("NOTA DE NEGOCIAÇÃO")
        except ValueError:
            return []

        cells = lines[start:end]
        if len(cells) < 8:
            return []

        operations: list[Operation] = []
        for operation_cells in self._operation_segments(cells):
            operation = self._operation_from_cells(operation_cells)
            if operation is not None:
                operations.append(operation)
        return operations

    def _operation_segments(self, cells: list[str]) -> list[list[str]]:
        segments: list[list[str]] = []
        current: list[str] = []
        for cell in cells:
            if self._is_negotiation_cell(cell) and current:
                segments.append(current)
                current = []
            current.append(cell)
        if current:
            segments.append(current)
        return segments

    def _operation_from_cells(self, cells: list[str]) -> Operation | None:
        negotiation = cells[0] if cells else None
        side = self._side(cells[1]) if len(cells) > 1 else None
        market = cells[2] if len(cells) > 2 else None
        cursor = 3
        exercise_side = None
        if market == "EXERC OPC" and cursor < len(cells) and cells[cursor] in {"COMPRA", "VENDA"}:
            exercise_side = self._exercise_side(cells[cursor])
            cursor += 1

        term = None
        if cursor < len(cells) and re.fullmatch(r"\d{2}/\d{2}", cells[cursor]):
            term = cells[cursor]
            cursor += 1

        if len(cells) - cursor < 5:
            return None

        title_parts = cells[cursor:-4]
        title = " ".join(title_parts) or None
        quantity = self._decimal(cells[-4])
        price = self._decimal(cells[-3])
        total = self._decimal(cells[-2])
        debit_credit = cells[-1]
        raw = " | ".join(cells)
        observation = self._operation_observation(title_parts, exercise_side)
        return Operation(
            raw=raw,
            negotiation=negotiation,
            side=side,
            market=market,
            term=term,
            title=title,
            observation=observation,
            strike=self._operation_strike(market, observation),
            quantity=quantity,
            price=price,
            total=total,
            debit_credit=self._debit_credit(debit_credit),
            asset=self._asset_from_title(title),
        )

    def _business_summary(self, lines: list[str]) -> dict[str, Any]:
        keys = [
            "debentures",
            "spot_sales",
            "spot_purchases",
            "options_purchases",
            "options_sales",
            "term_operations",
            "public_bonds_value",
            "operations_value",
        ]
        summary_idx = self._index_of(lines, "Resumo dos Negócios")
        if summary_idx is None:
            return {}
        values = [self._decimal(line) for line in lines[:summary_idx]]
        values = [value for value in values if value is not None]
        return {key: value for key, value in zip(keys, values[-len(keys):])}

    def _financial_summary(self, lines: list[str]) -> dict[str, Any]:
        labels = [
            ("total_cblc", "Total CBLC"),
            ("net_operations_value", "Valor líquido das operações"),
            ("settlement_fee", "Taxa de liquidação"),
            ("registration_fee", "Taxa de Registro"),
            ("bovespa_total", "Total Bovespa / Soma"),
            ("term_options_fee", "Taxa de termo/opções"),
            ("ana_fee", "Taxa A.N.A."),
            ("emoluments", "Emolumentos"),
            ("total_costs", "Total Custos / Despesas"),
            ("operational_fee", "Taxa Operacional"),
            ("execution", "Execução"),
            ("custody_fee", "Taxa de Custódia"),
            ("taxes", "Impostos"),
            ("irrf", "I.R.R.F. s/ operações"),
            ("other", "Outros"),
        ]
        summary: dict[str, Any] = {}
        for key, label in labels:
            value = self._money_before_label(lines, label)
            if value is not None:
                summary[key] = value
            dc = self._debit_credit_after_label(lines, label)
            if dc is not None:
                summary[f"{key}_debit_credit"] = dc

        liquid_idx = self._index_matching(lines, r"Líquido para\s+(\d{2}/\d{2}/\d{4})")
        if liquid_idx is not None:
            date_match = re.search(r"(\d{2}/\d{2}/\d{4})", lines[liquid_idx])
            if date_match:
                summary["settlement_date"] = date_match.group(1)
            value = self._previous_decimal(lines, liquid_idx)
            if value is not None:
                summary["net_settlement"] = value
            if liquid_idx + 1 < len(lines):
                summary["net_settlement_debit_credit"] = self._debit_credit(lines[liquid_idx + 1])
        return {key: value for key, value in summary.items() if value is not None}

    def _layout_version(self, text: str) -> str:
        normalized = text.upper()
        if "NOTA DE NEGOCIAÇÃO" in normalized or "NOTA DE NEGOCIACAO" in normalized:
            return "clear-note-negotiation-v1"
        return "unknown"

    def _note_type(self, operations: list[Operation]) -> BrokerNoteType:
        found = set()
        for operation in operations:
            value = f"{operation.market or ''} {operation.title or ''} {operation.asset or ''}".upper()
            if "OPCAO" in value or "OPÇÃO" in value or "OPC" in value:
                found.add(BrokerNoteType.OPTIONS)
            elif "ETF" in value:
                found.add(BrokerNoteType.ETFS)
            elif operation.asset and operation.asset.endswith("11"):
                found.add(BrokerNoteType.FIIS)
            elif operation.asset or "VISTA" in value or "FRACIONARIO" in value:
                found.add(BrokerNoteType.STOCKS)
        if len(found) > 1:
            return BrokerNoteType.MIXED
        return next(iter(found), BrokerNoteType.UNKNOWN)

    def _lines(self, text: str) -> list[str]:
        return [" ".join(line.split()) for line in text.splitlines() if line.strip()]

    def _value_after(self, lines: list[str], label: str) -> str | None:
        idx = self._index_of(lines, label)
        if idx is None or idx + 1 >= len(lines):
            return None
        return lines[idx + 1]

    def _yes_no_after(self, lines: list[str], label: str) -> bool | None:
        value = self._value_after(lines, label)
        if value == "S":
            return True
        if value == "N":
            return False
        return None

    def _index_of(self, lines: list[str], label: str) -> int | None:
        try:
            return lines.index(label)
        except ValueError:
            return None

    def _index_matching(self, lines: list[str], pattern: str) -> int | None:
        for index, line in enumerate(lines):
            if re.search(pattern, line, flags=re.IGNORECASE):
                return index
        return None

    def _first_line_matching(self, lines: list[str], pattern: str) -> str | None:
        idx = self._index_matching(lines, pattern)
        return lines[idx] if idx is not None else None

    def _first_match(self, text: str, pattern: str) -> str | None:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        return match.group(1) if match else None

    def _customer_document(self, lines: list[str]) -> str | None:
        idx = self._index_of(lines, "C.P.F./C.N.P.J/C.V.M./C.O.B.")
        if idx is None:
            return None
        for candidate in reversed(lines[:idx]):
            if re.fullmatch(r"\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", candidate):
                return candidate
        return None

    def _address_after(self, lines: list[str], line: str | None) -> str | None:
        if line is None:
            return None
        idx = self._index_of(lines, line)
        if idx is None:
            return None
        parts = lines[idx + 1 : idx + 4]
        return ", ".join(parts) if parts else None

    def _money_before_label(self, lines: list[str], label: str) -> Decimal | None:
        idx = self._index_matching(lines, rf"^{re.escape(label)}")
        if idx is None:
            return None
        return self._previous_decimal(lines, idx)

    def _previous_decimal(self, lines: list[str], before_index: int) -> Decimal | None:
        for candidate in reversed(lines[:before_index]):
            value = self._decimal(candidate)
            if value is not None:
                return value
        return None

    def _debit_credit_after_label(self, lines: list[str], label: str) -> str | None:
        idx = self._index_matching(lines, rf"^{re.escape(label)}")
        if idx is None:
            return None
        for candidate in lines[idx + 1 : idx + 3]:
            dc = self._debit_credit(candidate)
            if dc is not None:
                return dc
        return None

    def _merge_dicts(self, summaries) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for summary in summaries:
            for key, value in summary.items():
                if isinstance(value, Decimal) and isinstance(merged.get(key), Decimal):
                    merged[key] += value
                elif key not in merged or merged[key] in (None, Decimal("0")):
                    merged[key] = value
        return merged

    def _operation_observation(self, title_parts: list[str], exercise_side: str | None = None) -> str | None:
        parts = []
        if exercise_side is not None:
            parts.append(f"exercise_side={exercise_side.lower()}")
        if len(title_parts) > 1:
            parts.append(" ".join(title_parts[1:]))
        return " | ".join(parts) if parts else None

    def _operation_strike(self, market: str | None, observation: str | None) -> Decimal | None:
        if market not in {"OPCAO DE COMPRA", "OPCAO DE VENDA"} or observation is None:
            return None
        match = re.match(r"^(\d{1,3}(?:\.\d{3})*,\d{2,8}|\d+,\d{2,8}|\d+)(?:\s|$)", observation)
        if not match:
            return None
        return self._decimal(match.group(1))

    def _is_negotiation_cell(self, value: str) -> bool:
        return bool(re.fullmatch(r"\d+-[A-Z]+", value))

    def _asset_from_title(self, title: str | None) -> str | None:
        if not title:
            return None
        token = title.split()[0]
        if re.fullmatch(r"[A-Z]{4,5}\d{1,3}[A-Z0-9]*", token):
            return token
        return token if token.isalpha() else None

    def _side(self, value: str | None) -> str | None:
        return {"C": "buy", "V": "sell"}.get(value or "")

    def _exercise_side(self, value: str | None) -> str | None:
        return {"COMPRA": "buy", "VENDA": "sell"}.get(value or "")

    def _debit_credit(self, value: str | None) -> str | None:
        return {"D": "debit", "C": "credit"}.get(value or "")

    def _int_or_none(self, value: str | None) -> int | None:
        try:
            return int(value) if value is not None else None
        except ValueError:
            return None

    def _decimal(self, value: str | None) -> Decimal | None:
        if value is None or not re.fullmatch(r"\d+|\d{1,3}(?:\.\d{3})*,\d{2,8}|\d+,\d{2,8}", value):
            return None
        try:
            return Decimal(value.replace(".", "").replace(",", "."))
        except (InvalidOperation, AttributeError):
            return None
