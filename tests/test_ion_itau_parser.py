from pathlib import Path

from brokerage.brokers.ion_itau import IonItauParser
from brokerage.models import BrokerNoteType, ExtractedPdf
from brokerage.parser import PARSERS
from brokerage.summary import summarize_payload

FIXTURES = Path(__file__).parent / "fixtures" / "ion_itau"
FRACTIONAL_SHEET = (FIXTURES / "fractional_sheet.txt").read_text()


def test_ion_itau_parser_is_discovered_dynamically():
    assert any(parser.__class__.__name__ == "IonItauParser" for parser in PARSERS)


def test_ion_itau_parser_extracts_fractional_note():
    parsed = IonItauParser().parse(
        ExtractedPdf(
            source_file=Path("sample.pdf"),
            text=FRACTIONAL_SHEET,
            pages=1,
            page_texts=[FRACTIONAL_SHEET],
            used_password=True,
        )
    )

    assert parsed.broker.name == "Ion Itaú"
    assert parsed.broker.legal_name == "Itaú Corretora de Valores S/A"
    assert parsed.broker.document == "00.000.000/0001-00"
    assert parsed.layout_version == "ion-itau-note-b3-v1"
    assert parsed.pages == 1
    assert parsed.used_password is True
    assert parsed.customer.name == "CLIENTE TESTE"
    assert parsed.customer.document == "000.000.000-00"
    assert parsed.customer.code == "999999-1"
    assert parsed.customer.advisor_code == "77"
    assert len(parsed.notes) == 1

    note = parsed.notes[0]
    assert note.number == "800001"
    assert note.sheet_count == 1
    assert note.pdf_pages == [1]
    assert note.trade_date == "02/06/2026"
    assert note.settlement_date == "04/06/2026"
    assert note.broker_note_type == BrokerNoteType.STOCKS
    assert note.assets == ["ACME", "BRASIL"]

    assert len(note.operations) == 2
    first, second = note.operations
    assert first.raw.startswith("B3 RV LISTADO C FRACIONARIO")
    assert first.negotiation == "B3 RV LISTADO"
    assert first.side == "buy"
    assert first.market == "FRACIONARIO"
    assert first.title == "BRASIL ON EJ"
    assert first.observation == "EJ"
    assert first.asset == "BRASIL"
    assert str(first.quantity) == "10"
    assert str(first.price) == "12.34"
    assert str(first.total) == "123.40"
    assert first.debit_credit == "debit"
    assert second.side == "sell"
    assert str(second.quantity) == "5"
    assert str(second.price) == "20.00"
    assert str(second.total) == "100.00"
    assert second.debit_credit == "credit"


def test_ion_itau_parser_supports_compact_money_from_pdf_text():
    operation = IonItauParser()._operation_from_line(
        "B3 RV LISTADO C FRACIONARIO TESTE ON EJ 3 1234 3702 D"
    )

    assert operation is not None
    assert str(operation.quantity) == "3"
    assert str(operation.price) == "12.34"
    assert str(operation.total) == "37.02"


def test_ion_itau_parser_extracts_business_and_financial_summaries():
    note = IonItauParser().parse(
        ExtractedPdf(source_file=Path("sample.pdf"), text=FRACTIONAL_SHEET, pages=1, page_texts=[FRACTIONAL_SHEET])
    ).notes[0]

    assert note.business_summary["spot_sales"].to_eng_string() == "100.00"
    assert note.business_summary["spot_purchases"].to_eng_string() == "123.40"
    assert note.business_summary["operations_value"].to_eng_string() == "223.40"
    assert note.financial_summary["net_operations_value"].to_eng_string() == "23.40"
    assert note.financial_summary["settlement_fee"].to_eng_string() == "0.05"
    assert note.financial_summary["registration_fee"].to_eng_string() == "0.03"
    assert note.financial_summary["emoluments"].to_eng_string() == "0.02"
    assert note.financial_summary["net_settlement"].to_eng_string() == "23.50"
    assert note.financial_summary["net_settlement_debit_credit"] == "debit"


def test_ion_itau_summary_groups_by_note_and_asset_with_allocated_costs():
    parsed = IonItauParser().parse(
        ExtractedPdf(source_file=Path("sample.pdf"), text=FRACTIONAL_SHEET, pages=1, page_texts=[FRACTIONAL_SHEET])
    )

    summary = summarize_payload(parsed)

    assert "Broker: Ion Itaú" in summary
    assert "Note 800001 | type=stocks | trade_date=02/06/2026 | settlement_date=04/06/2026 | sheets=1 | pages=1" in summary
    assert "Financial: irrf=$0.00 | settlement_fee=$0.05 | emoluments=$0.02 | operational_fee=$0.00 | registration_fee=$0.03 | transfer_fee=$0.00 | allocated_costs=$0.10" in summary
    assert 'ACME | $100.00 / 5 = $20.00 (1 operations, side=sell, market="FRACIONARIO", dc=credit, allocated_costs=$0.04)' in summary
    assert 'BRASIL | $123.40 / 10 = $12.34 (1 operations, side=buy, market="FRACIONARIO", dc=debit, allocated_costs=$0.06)' in summary
