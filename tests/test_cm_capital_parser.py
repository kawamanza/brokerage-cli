from pathlib import Path

from brokerage.brokers.cm_capital import CmCapitalParser
from brokerage.models import BrokerNoteType, ExtractedPdf
from brokerage.parser import PARSERS

FIXTURES = Path(__file__).parent / "fixtures" / "cm_capital"
OPTION_SALE_SHEET = (FIXTURES / "options_sale_sheet.txt").read_text()
OPTION_SALE_CELLS = (FIXTURES / "options_sale_cells.txt").read_text()


def test_cm_capital_parser_extracts_option_sale_note():
    parser = CmCapitalParser()

    parsed = parser.parse(
        ExtractedPdf(
            source_file=Path("sample.pdf"),
            text=OPTION_SALE_SHEET,
            pages=1,
            page_texts=[OPTION_SALE_SHEET],
            used_password=True,
        )
    )

    assert parsed.broker.name == "CM Capital"
    assert parsed.layout_version == "cm-capital-note-b3-v1"
    assert parsed.pages == 1
    assert parsed.used_password is True
    assert parsed.customer.name == "CLIENTE TESTE"
    assert parsed.customer.document == "000.000.000-00"
    assert parsed.customer.code == "999999-1"
    assert parsed.customer.advisor_code == "80"
    assert len(parsed.notes) == 1

    note = parsed.notes[0]
    assert note.number == "900001"
    assert note.sheet_count == 1
    assert note.pdf_pages == [1]
    assert note.trade_date == "20/03/2026"
    assert note.settlement_date == "23/03/2026"
    assert note.broker_note_type == BrokerNoteType.OPTIONS
    assert note.business_summary["options_sales"] == note.operations[0].total
    assert note.financial_summary["settlement_fee"].to_eng_string() == "0.01"
    assert note.financial_summary["registration_fee"].to_eng_string() == "0.04"
    assert note.financial_summary["emoluments"].to_eng_string() == "0.02"
    assert note.financial_summary["net_settlement_debit_credit"] == "credit"

    operation = note.operations[0]
    assert operation.raw.startswith("BOVESPA V OPÇÃO DE VENDA")
    assert operation.negotiation == "BOVESPA"
    assert operation.side == "sell"
    assert operation.market == "OPCAO DE VENDA"
    assert operation.term == "03/26"
    assert operation.asset == "ABCDO879"
    assert operation.title == "ABCDO879 ON 8,37 ABCDE"
    assert operation.observation == "8,37 ABCDE"
    assert str(operation.strike) == "8.37"
    assert str(operation.quantity) == "500"
    assert str(operation.price) == "0.12"
    assert str(operation.total) == "60.00"
    assert operation.debit_credit == "credit"


def test_cm_capital_parser_is_discovered_dynamically():
    assert any(parser.__class__.__name__ == "CmCapitalParser" for parser in PARSERS)


def test_cm_capital_parser_supports_cell_extracted_tables():
    parsed = CmCapitalParser().parse(
        ExtractedPdf(
            source_file=Path("sample.pdf"),
            text=OPTION_SALE_CELLS,
            pages=1,
            page_texts=[OPTION_SALE_CELLS],
        )
    )

    note = parsed.notes[0]
    operation = note.operations[0]

    assert note.number == "900001"
    assert note.trade_date == "20/03/2026"
    assert note.settlement_date == "23/03/2026"
    assert note.business_summary["options_sales"].to_eng_string() == "60.00"
    assert note.financial_summary["settlement_fee"].to_eng_string() == "0.01"
    assert operation.asset == "ABCDO879"
    assert operation.title == "ABCDO879 ON 8,37 ABCDE"
    assert operation.observation == "8,37 ABCDE"
    assert str(operation.strike) == "8.37"
