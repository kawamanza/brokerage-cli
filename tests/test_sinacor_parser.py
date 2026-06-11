from pathlib import Path

from brokerage.brokers.sinacor import SinacorParser
from brokerage.models import BrokerNoteType, ExtractedPdf
from brokerage.parser import PARSERS
from brokerage.summary import summarize_payload

FIXTURES = Path(__file__).parent / "fixtures" / "sinacor"
SHEET = (FIXTURES / "nu_invest_sheet.txt").read_text()


def test_sinacor_parser_is_discovered_dynamically():
    assert any(parser.__class__.__name__ == "SinacorParser" for parser in PARSERS)


def test_sinacor_parser_extracts_b3_note():
    parsed = SinacorParser().parse(
        ExtractedPdf(source_file=Path("sample.pdf"), text=SHEET, pages=1, page_texts=[SHEET], used_password=True)
    )

    assert parsed.broker.name == "SINACOR"
    assert parsed.broker.legal_name == "NU INVESTIMENTOS S.A - CTVM"
    assert parsed.broker.document == "00.000.000/0001-00"
    assert parsed.layout_version == "sinacor-note-b3-v1"
    assert parsed.used_password is True
    assert parsed.customer.name == "CLIENTE TESTE"
    assert parsed.customer.document == "000.000.000-00"
    assert parsed.customer.code == "999-1"
    assert parsed.customer.advisor_code == "80"

    note = parsed.notes[0]
    assert note.number == "900001"
    assert note.sheet_count == 1
    assert note.pdf_pages == [1]
    assert note.trade_date == "31/03/2026"
    assert note.settlement_date == "02/04/2026"
    assert note.broker_note_type == BrokerNoteType.FIIS
    assert note.assets == ["FII TESTE"]

    operation = note.operations[0]
    assert operation.raw.startswith("B3 RV LISTADO V VISTA")
    assert operation.negotiation == "B3 RV LISTADO"
    assert operation.side == "sell"
    assert operation.market == "VISTA"
    assert operation.title == "FII TESTE CI @"
    assert operation.observation == "CI @"
    assert operation.asset == "FII TESTE"
    assert str(operation.quantity) == "10"
    assert str(operation.price) == "12.34"
    assert str(operation.total) == "123.40"
    assert operation.debit_credit == "credit"


def test_sinacor_parser_extracts_summaries_and_summary_output():
    parsed = SinacorParser().parse(ExtractedPdf(source_file=Path("sample.pdf"), text=SHEET, pages=1, page_texts=[SHEET]))
    note = parsed.notes[0]

    assert note.business_summary["spot_sales"].to_eng_string() == "123.40"
    assert note.business_summary["operations_value"].to_eng_string() == "123.40"
    assert note.financial_summary["net_operations_value"].to_eng_string() == "123.40"
    assert note.financial_summary["net_operations_value_debit_credit"] == "credit"
    assert note.financial_summary["settlement_fee"].to_eng_string() == "0.03"
    assert note.financial_summary["settlement_fee_debit_credit"] == "debit"
    assert note.financial_summary["registration_fee"].to_eng_string() == "0.01"
    assert note.financial_summary["emoluments"].to_eng_string() == "0.02"
    assert note.financial_summary["net_settlement"].to_eng_string() == "123.34"
    assert note.financial_summary["net_settlement_debit_credit"] == "credit"

    summary = summarize_payload(parsed)
    assert "Broker: SINACOR (NU INVESTIMENTOS S.A - CTVM)" in summary
    assert "Financial: irrf=$0.00 | settlement_fee=$0.03 | emoluments=$0.02 | operational_fee=$0.00 | registration_fee=$0.01 | transfer_fee=$0.00 | allocated_costs=$0.06" in summary
    assert 'FII TESTE | $123.40 / 10 = $12.34 (1 operations, side=sell, market="VISTA", dc=credit, allocated_costs=$0.06)' in summary
