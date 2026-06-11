from __future__ import annotations

import re
import unicodedata
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


class NuInvestParser:
    broker_name = "Nu Investimentos"
    layout_version = "nu-investimentos-note-v1"

    def matches(self, text: str) -> bool:
        normalized = self._normalize(text).upper()
        return (
            "NU INVESTIMENTOS S.A. - CORRETORA DE TITULOS E VALORES MOBILIARIOS" in normalized
            and "DATA PREGAO" in normalized
            and "NUMERO DA NOTA" in normalized
            and "RESUMO FINANCEIRO" in normalized
        )

    def parse(self, extracted: ExtractedPdf) -> BrokerageFile:
        page_texts = extracted.page_texts or extracted.text.split("\f") or [extracted.text]
        sheets = [self._parse_sheet(text, index) for index, text in enumerate(page_texts, start=1) if text.strip()]
        notes = self._group_notes(sheets)
        warnings: list[str] = []
        if not notes:
            warnings.append("No negotiation notes were parsed from the extracted text.")

        return BrokerageFile(
            broker=self._broker_info(extracted.text),
            layout_version=self.layout_version,
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
        header = self._header(lines)
        operations = self._operations(lines)
        financial_summary = self._financial_summary(lines)
        header["settlement_date"] = financial_summary.get("settlement_date")
        warnings: list[str] = []
        if not operations:
            warnings.append("No operations were parsed from this sheet.")

        return header, Sheet(
            pdf_page=pdf_page,
            sheet_number=header.get("sheet_number"),
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
                    computed={"operation_count": len(operations), "asset_count": len(assets)},
                    warnings=[warning for sheet in sheets for warning in sheet.warnings],
                )
            )
        return notes

    def _header(self, lines: list[str]) -> dict[str, Any]:
        sheet_value = self._value_after(lines, "Folha")
        sheet_match = re.match(r"(\d+)", sheet_value or "")
        return {
            "number": self._value_after(lines, "Número da nota"),
            "sheet_number": self._int_or_none(sheet_match.group(1) if sheet_match else None),
            "trade_date": self._value_after(lines, "Data Pregão"),
        }

    def _broker_info(self, text: str) -> BrokerInfo:
        lines = self._lines(text)
        legal_name = self._first_line_matching(lines, r"Nu Investimentos S\.A\. - Corretora de Títulos e Valores Mobiliários")
        return BrokerInfo(
            name=self.broker_name,
            legal_name=legal_name,
            document=self._first_match(text, r"CNPJ:\s*([\d\./-]+)"),
            address=self._address_after(lines, legal_name),
            phones=re.findall(r"\d{4}\s+\d{4}\s+\d{4}|\d{3,4}-\d{3,4}-\d{3,4}|\d{4}-\d{4}", text),
            website=self._first_match(text, r"\|\s*(www\.[^\s]+)"),
            ombudsman_phone=self._first_match(text, r"Ouvidoria.*?(\d{4}\s+\d{4}\s+\d{4}|\d{3,4}-\d{3,4}-\d{3,4})"),
        )

    def _customer_info(self, text: str) -> CustomerInfo:
        lines = self._lines(text)
        address_idx = self._index_of(lines, "Endereço")
        address = None
        if address_idx is not None:
            parts = []
            for candidate in lines[address_idx + 1 : address_idx + 6]:
                if candidate in {"Mercado C/V Tipo de Mercado Especificação do Título Observação Quantidade Preço/Ajuste Valor/Ajuste D/C", "Cidade", "UF", "CEP"}:
                    break
                parts.append(candidate)
            address = ", ".join(parts) if parts else None
        return CustomerInfo(
            code=self._value_after(lines, "Código do Cliente"),
            name=self._value_after(lines, "Nome do Cliente"),
            document=self._value_after(lines, "CPF"),
            address=address,
        )

    def _operations(self, lines: list[str]) -> list[Operation]:
        start = self._index_matching(lines, r"^Mercado C/V Tipo de Mercado")
        end = self._index_of(lines, "Resumo dos Negócios")
        if start is None or end is None or start >= end:
            return []
        return [operation for line in lines[start + 1 : end] if (operation := self._operation_from_line(line)) is not None]

    def _operation_from_line(self, line: str) -> Operation | None:
        pattern = re.compile(
            r"^(?P<negotiation>BOVESPA)\s+"
            r"(?P<side>[CV])\s+"
            r"(?P<market>FRACIONARIO|FRACIONÁRIO|VISTA)\s+"
            r"(?P<title>.+?)\s+"
            r"(?P<quantity>\d+)\s+"
            r"R\$\s*(?P<price>\d{1,3}(?:\.\d{3})*,\d{2,8}|\d+,\d{2,8})\s+"
            r"R\$\s*(?P<total>\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})\s+"
            r"(?P<dc>[DC])$"
        )
        match = pattern.match(line)
        if not match:
            return None
        market = self._normalize_market(match.group("market"))
        title = match.group("title")
        observation = self._operation_observation(title)
        return Operation(
            raw=line,
            negotiation=match.group("negotiation"),
            side=self._side(match.group("side")),
            market=market,
            title=title,
            observation=observation,
            quantity=self._decimal(match.group("quantity")),
            price=self._decimal(match.group("price")),
            total=self._decimal(match.group("total")),
            debit_credit=self._debit_credit(match.group("dc")),
            asset=self._asset_from_title(title),
        )

    def _business_summary(self, lines: list[str]) -> dict[str, Any]:
        labels = [
            ("debentures", "Debêntures"),
            ("spot_sales", "Vendas à vista"),
            ("spot_purchases", "Compras à vista"),
            ("options_purchases", "Opções - Compras"),
            ("options_sales", "Opções - Vendas"),
            ("term_operations", "Operações a Termo"),
            ("public_bonds_value", "Valor das Operações com Títulos Públicos (V. Nom.)"),
            ("operations_value", "Valor das Operações"),
        ]
        return self._labeled_money_values(lines, labels)

    def _financial_summary(self, lines: list[str]) -> dict[str, Any]:
        labels = [
            ("net_operations_value", "Valor Líquido das Operações"),
            ("settlement_fee", "Taxa de Liquidação/CCP"),
            ("registration_fee", "Taxa de Registro"),
            ("term_options_fee", "Taxa de Termo / Opções"),
            ("ana_fee", "Taxa A.N.A."),
            ("emoluments", "Emolumentos"),
            ("transfer_fee", "Taxa de Transferência de Ativos"),
            ("taxes", "ISS"),
            ("irrf", "I.R.R.F. s/ operações."),
            ("other", "Outras"),
        ]
        summary = self._labeled_money_values(lines, labels, with_sign_debit_credit=True)
        liquid_idx = self._index_matching(lines, r"^Líquido para")
        if liquid_idx is not None:
            match = re.fullmatch(
                r"Líquido para\s+(?P<date>\d{2}/\d{2}/\d{4})\s+R\$\s*(?P<value>\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})",
                lines[liquid_idx],
            )
            if match:
                summary["settlement_date"] = match.group("date")
                summary["net_settlement"] = self._decimal(match.group("value"))
        return {key: value for key, value in summary.items() if value is not None}

    def _labeled_money_values(
        self,
        lines: list[str],
        labels: list[tuple[str, str]],
        *,
        with_sign_debit_credit: bool = False,
    ) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for key, label in labels:
            pattern = rf"^{re.escape(label)}(?:\s+Base\s+R\$\s*(?:\d{{1,3}}(?:\.\d{{3}})*,\d{{2}}|\d+,\d{{2}}))?\s+(?P<sign>-)?R\$\s*(?P<value>\d{{1,3}}(?:\.\d{{3}})*,\d{{2}}|\d+,\d{{2}})$"
            for line in lines:
                match = re.fullmatch(pattern, line, flags=re.IGNORECASE)
                if not match:
                    continue
                values[key] = self._decimal(match.group("value"))
                if with_sign_debit_credit and match.group("sign"):
                    values[f"{key}_debit_credit"] = "debit"
                break
        return values

    def _note_type(self, operations: list[Operation]) -> BrokerNoteType:
        found = set()
        for operation in operations:
            value = f"{operation.market or ''} {operation.title or ''} {operation.asset or ''}".upper()
            if "OPCAO" in value or "OPÇÃO" in value or "OPC" in value:
                found.add(BrokerNoteType.OPTIONS)
            elif "ETF" in value:
                found.add(BrokerNoteType.ETFS)
            elif "FII" in value or (operation.asset and operation.asset.endswith("11")):
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

    def _address_after(self, lines: list[str], line: str | None) -> str | None:
        if line is None:
            return None
        idx = self._index_of(lines, line)
        if idx is None:
            return None
        parts = []
        for candidate in lines[idx + 1 : idx + 5]:
            if re.search(r"CNPJ|Data Pregão", candidate, flags=re.IGNORECASE):
                break
            parts.append(candidate)
        return ", ".join(parts) if parts else None

    def _operation_observation(self, title: str | None) -> str | None:
        if not title:
            return None
        tokens = title.split()
        if len(tokens) <= 1:
            return None
        if tokens[0] == "FII" and len(tokens) > 2:
            return " ".join(tokens[2:]) or None
        while len(tokens) > 1 and tokens[1] in {"ON", "PN", "UNT", "CI"}:
            tokens.pop(1)
        return " ".join(tokens[1:]) if len(tokens) > 1 else None

    def _asset_from_title(self, title: str | None) -> str | None:
        if not title:
            return None
        tokens = title.split()
        if len(tokens) >= 2 and tokens[0] == "FII":
            return " ".join(tokens[:2])
        return tokens[0]

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
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        return match.group(1) if match else None

    def _side(self, value: str | None) -> str | None:
        return {"C": "buy", "V": "sell"}.get(value or "")

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

    def _merge_dicts(self, summaries) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for summary in summaries:
            for key, value in summary.items():
                if isinstance(value, Decimal) and isinstance(merged.get(key), Decimal):
                    merged[key] += value
                elif key not in merged or merged[key] in (None, Decimal("0")):
                    merged[key] = value
        return merged

    def _normalize_market(self, value: str) -> str:
        return self._normalize(value).upper().replace("FRACIONÁRIO", "FRACIONARIO")

    def _normalize(self, value: str) -> str:
        return "".join(char for char in unicodedata.normalize("NFKD", value) if not unicodedata.combining(char))
