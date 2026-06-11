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


class SinacorParser:
    broker_name = "SINACOR"
    layout_version = "sinacor-note-b3-v1"

    def matches(self, text: str) -> bool:
        normalized = self._normalize(text).upper()
        return (
            "NOTA DE NEGOCIACAO" in normalized
            and "NR. NOTA FOLHA DATA PREGAO" in normalized
            and "Q NEGOCIACAO C/V TIPO MERCADO" in normalized
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
        idx = self._index_matching(lines, r"^Nr\. Nota Folha Data pregão")
        if idx is None or idx + 1 >= len(lines):
            return {}
        match = re.fullmatch(r"(?P<number>\d+)\s+(?P<sheet>\d+)\s+(?P<trade_date>\d{2}/\d{2}/\d{4})", lines[idx + 1])
        if not match:
            return {}
        return {
            "number": match.group("number"),
            "sheet_number": self._int_or_none(match.group("sheet")),
            "trade_date": match.group("trade_date"),
        }

    def _broker_info(self, text: str) -> BrokerInfo:
        lines = self._lines(text)
        legal_name = self._legal_name(lines)
        return BrokerInfo(
            name=self.broker_name,
            legal_name=legal_name,
            document=self._first_match(text, r"C\.N\.P\.J\.:\s*([\d\./-]+)"),
            address=self._address_after(lines, legal_name),
            phones=re.findall(r"\d{3,4}-\d{3,4}-\d{3,4}|\d{4}-\d{4}|\(?\d{2}\)?\s*\d{4,5}-\d{4}", text),
            website=self._first_match(text, r"Internet:\s*(\S+)"),
            ombudsman_phone=self._first_match(text, r"Ouvidoria:\s*Tel\.\s*([\d\-]+)"),
        )

    def _customer_info(self, text: str) -> CustomerInfo:
        lines = self._lines(text)
        customer_idx = self._index_of(lines, "Cliente")
        customer_line = lines[customer_idx + 1] if customer_idx is not None and customer_idx + 1 < len(lines) else None
        code = None
        name = None
        if customer_line:
            match = re.match(r"(?P<code>\d+\s*-\s*\d+)\s+(?P<name>.+)", customer_line)
            if match:
                code = match.group("code").replace(" ", "")
                name = match.group("name")
            else:
                name = customer_line

        code_idx = self._index_matching(lines, r"^Código cliente Assessor")
        advisor_code = None
        if code_idx is not None and code_idx + 1 < len(lines):
            tokens = re.findall(r"\d+\s*-\s*\d+|\d+", lines[code_idx + 1])
            if tokens:
                code = code or tokens[0].replace(" ", "")
            if len(tokens) >= 2:
                advisor_code = tokens[-1].replace(" ", "")

        document_idx = self._index_of(lines, "C.P.F./C.N.P.J./C.V.M./C.O.B.")
        document = lines[document_idx + 1] if document_idx is not None and document_idx + 1 < len(lines) else None
        return CustomerInfo(code=code, name=name, document=document, advisor_code=advisor_code)

    def _operations(self, lines: list[str]) -> list[Operation]:
        start = self._index_matching(lines, r"^Q Negociação C/V Tipo mercado")
        end = self._index_matching(lines, r"^Resumo dos Negócios")
        if start is None or end is None or start >= end:
            return []
        return [operation for line in lines[start + 1 : end] if (operation := self._operation_from_line(line)) is not None]

    def _operation_from_line(self, line: str) -> Operation | None:
        pattern = re.compile(
            r"^(?P<negotiation>B3\s+RV\s+LISTADO)\s+"
            r"(?P<side>[CV])\s+"
            r"(?P<market>FRACIONARIO|FRACIONÁRIO|VISTA)\s+"
            r"(?:(?P<term>\d{2}/\d{2})\s+)?"
            r"(?P<title>.+?)\s+"
            r"(?P<quantity>\d+)\s+"
            r"(?P<price>\d{1,3}(?:\.\d{3})*,\d{2,8}|\d+,\d{2,8}|\d+)\s+"
            r"(?P<total>\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}|\d+)\s+"
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
            term=match.group("term"),
            title=title,
            observation=observation,
            quantity=self._decimal(match.group("quantity")),
            price=self._money_decimal(match.group("price")),
            total=self._money_decimal(match.group("total")),
            debit_credit=self._debit_credit(match.group("dc")),
            asset=self._asset_from_title(title),
        )

    def _business_summary(self, lines: list[str]) -> dict[str, Any]:
        labels = [
            ("debentures", "Debêntures"),
            ("spot_sales", "Vendas à vista"),
            ("spot_purchases", "Compras à vista"),
            ("options_purchases", "Opções - compras"),
            ("options_sales", "Opções - vendas"),
            ("term_operations", "Operações à termo"),
            ("public_bonds_value", "Valor das oper. c/ títulos públ. (v. nom.)"),
            ("operations_value", "Valor das operações"),
        ]
        return self._labeled_values(lines, labels)

    def _financial_summary(self, lines: list[str]) -> dict[str, Any]:
        labels = [
            ("net_operations_value", "Valor líquido das operações"),
            ("settlement_fee", "Taxa de liquidação/CCP"),
            ("registration_fee", "Taxa de Registro"),
            ("term_options_fee", "Taxa de termo/opções"),
            ("ana_fee", "Taxa A.N.A."),
            ("emoluments", "Emolumentos"),
            ("transfer_fee", "Taxa de Transferência de Ativos"),
            ("clearing", "Clearing"),
            ("execution", "Execução"),
            ("taxes", "ISS"),
            ("other", "Outras"),
        ]
        summary = self._labeled_values(lines, labels, with_debit_credit=True)
        liquid_idx = self._index_matching(lines, r"^Líquido para")
        if liquid_idx is not None:
            match = re.fullmatch(
                r"Líquido para\s+(?P<date>\d{2}/\d{2}/\d{4})\s+"
                r"(?P<value>\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}|\d+)\s+(?P<dc>[DC])",
                lines[liquid_idx],
            )
            if match:
                summary["settlement_date"] = match.group("date")
                summary["net_settlement"] = self._money_decimal(match.group("value"))
                summary["net_settlement_debit_credit"] = self._debit_credit(match.group("dc"))
        return {key: value for key, value in summary.items() if value is not None}

    def _labeled_values(self, lines: list[str], labels: list[tuple[str, str]], *, with_debit_credit: bool = False) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for key, label in labels:
            idx = self._index_matching(lines, rf"^{re.escape(label)}(?:\s+|$)")
            if idx is None:
                continue
            pattern = (
                rf"^{re.escape(label)}\s+(?P<value>\d{{1,3}}(?:\.\d{{3}})*,\d{{2}}|\d+,\d{{2}}|\d+)"
                rf"(?:\s+(?P<dc>[DC]))?$"
            )
            match = re.fullmatch(pattern, lines[idx], flags=re.IGNORECASE)
            if match:
                values[key] = self._money_decimal(match.group("value"))
                if with_debit_credit and match.group("dc"):
                    values[f"{key}_debit_credit"] = self._debit_credit(match.group("dc"))
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

    def _legal_name(self, lines: list[str]) -> str | None:
        for line in lines:
            if re.search(r"INVESTIMENTOS.*C[T]?VM|CORRETORA|DTVM|CTVM", line, flags=re.IGNORECASE):
                return line
        return None

    def _address_after(self, lines: list[str], line: str | None) -> str | None:
        if line is None:
            return None
        idx = self._index_of(lines, line)
        if idx is None:
            return None
        parts = []
        for candidate in lines[idx + 1 : idx + 4]:
            if re.search(r"C\.N\.P\.J|Internet|Cliente|NOTA", candidate, flags=re.IGNORECASE):
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

    def _first_match(self, text: str, pattern: str) -> str | None:
        match = re.search(pattern, text, flags=re.IGNORECASE)
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

    def _money_decimal(self, value: str | None) -> Decimal | None:
        parsed = self._decimal(value)
        if parsed is None:
            return None
        if value is not None and re.fullmatch(r"\d+", value):
            return (parsed / Decimal("100")).quantize(Decimal("0.01"))
        return parsed

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
