from pathlib import Path

from brokerage.brokers.nu_invest import NuInvestParser
from brokerage.models import BrokerNoteType, ExtractedPdf
from brokerage.parser import PARSERS
from brokerage.summary import summarize_payload

FIXTURES = Path(__file__).parent / "fixtures" / "nu_invest"
SHEET = (FIXTURES / "own_layout_sheet.txt").read_text()


def test_nu_invest_parser_is_discovered_dynamically():
    assert any(parser.__class__.__name__ == "NuInvestParser" for parser in PARSERS)


def test_nu_invest_parser_extracts_own_layout_note():
    parsed = NuInvestParser().parse(
        ExtractedPdf(source_file=Path("sample.pdf"), text=SHEET, pages=1, page_texts=[SHEET], used_password=True)
    )

    assert parsed.broker.name == "Nu Investimentos"
    assert parsed.broker.legal_name == "Nu Investimentos S.A. - Corretora de Títulos e Valores Mobiliários"
    assert parsed.broker.document == "00.000.000/0001-00"
    assert parsed.layout_version == "nu-investimentos-note-v1"
    assert parsed.used_password is True
    assert parsed.customer.name == "CLIENTE TESTE"
    assert parsed.customer.document == "000.000.000-00"
    assert parsed.customer.code == "999999"

    note = parsed.notes[0]
    assert note.number == "700001"
    assert note.sheet_count == 1
    assert note.pdf_pages == [1]
    assert note.trade_date == "31/03/2026"
    assert note.settlement_date == "02/04/2026"
    assert note.broker_note_type == BrokerNoteType.FIIS
    assert note.assets == ["TEST11"]

    operation = note.operations[0]
    assert operation.raw.startswith("BOVESPA V VISTA")
    assert operation.negotiation == "BOVESPA"
    assert operation.side == "sell"
    assert operation.market == "VISTA"
    assert operation.title == "TEST11 CI @"
    assert operation.observation == "@"
    assert operation.asset == "TEST11"
    assert str(operation.quantity) == "10"
    assert str(operation.price) == "12.34"
    assert str(operation.total) == "123.40"
    assert operation.debit_credit == "credit"


def test_nu_invest_parser_extracts_summaries_and_summary_output():
    parsed = NuInvestParser().parse(ExtractedPdf(source_file=Path("sample.pdf"), text=SHEET, pages=1, page_texts=[SHEET]))
    note = parsed.notes[0]

    assert note.business_summary["spot_sales"].to_eng_string() == "123.40"
    assert note.business_summary["operations_value"].to_eng_string() == "123.40"
    assert note.financial_summary["net_operations_value"].to_eng_string() == "123.40"
    assert note.financial_summary["settlement_fee"].to_eng_string() == "0.03"
    assert note.financial_summary["settlement_fee_debit_credit"] == "debit"
    assert note.financial_summary["registration_fee"].to_eng_string() == "0.01"
    assert note.financial_summary["emoluments"].to_eng_string() == "0.02"
    assert note.financial_summary["emoluments_debit_credit"] == "debit"
    assert note.financial_summary["irrf"].to_eng_string() == "0.01"
    assert note.financial_summary["net_settlement"].to_eng_string() == "123.33"

    summary = summarize_payload(parsed)
    assert "Broker: Nu Investimentos" in summary
    assert "Financial: irrf=$0.01 | settlement_fee=$0.03 | emoluments=$0.02 | operational_fee=$0.00 | registration_fee=$0.01 | transfer_fee=$0.00 | allocated_costs=$0.06" in summary
    assert 'TEST11 | $123.40 / 10 = $12.34 (1 operations, side=sell, market="VISTA", dc=credit, allocated_costs=$0.06)' in summary
