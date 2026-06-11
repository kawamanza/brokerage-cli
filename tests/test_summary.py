from decimal import Decimal
from pathlib import Path

from brokerage.brokers.clear import ClearParser
from brokerage.brokers.cm_capital import CmCapitalParser
from brokerage.models import BatchResult, BrokerageFile, BrokerInfo, ExtractedPdf, NegotiationNote, Operation
from brokerage.summary import summarize_payload

FIXTURES = Path(__file__).parent / "fixtures" / "clear"


def test_summary_groups_operations_by_note_and_asset():
    sheet = (FIXTURES / "multiple_options_sheet.txt").read_text()
    parsed = ClearParser().parse(
        ExtractedPdf(
            source_file=Path("sample.pdf"),
            text=sheet,
            pages=1,
            page_texts=[sheet],
        )
    )

    summary = summarize_payload(parsed)

    assert 'File: "sample.pdf"' in summary
    assert "Pages: 1 | Notes: 1 | Operations: 5" in summary
    assert "Note 100000003 | type=options | trade_date=15/05/2026 | settlement_date=19/05/2026 | sheets=1 | pages=1" in summary
    assert "Financial: irrf=$0.00 | settlement_fee=$0.30 | emoluments=$0.00 | operational_fee=$0.00 | registration_fee=$0.00 | allocated_costs=$0.30" in summary
    assert 'ABCDH19 | $54.00 / 900 = $0.06 (3 operations, side=buy, market="OPCAO DE COMPRA", dc=debit, allocated_costs=$0.01, strike=$1.90)' in summary
    assert 'ABCDQ150W4 | $60.00 / 3000 = $0.02 (1 operations, side=buy, market="OPCAO DE VENDA", dc=debit, allocated_costs=$0.01, strike=$1.50)' in summary
    assert 'WXYZQ810E | $1620.00 / 200 = $8.10 (1 operations, side=buy, market="EXERC OPC", dc=debit, allocated_costs=$0.28)' in summary


def test_summary_renders_batch_errors():
    result = BatchResult(errors=[{"source_file": "bad.pdf", "error": "Unsupported"}])

    summary = summarize_payload(result)

    assert "Errors:" in summary
    assert "- bad.pdf: Unsupported" in summary


def test_summary_uses_human_title_for_non_option_assets():
    operation = ClearParser().parse(
        ExtractedPdf(
            source_file=Path("sample.pdf"),
            text=(FIXTURES / "stock_fractional_sheet.txt").read_text(),
            pages=1,
            page_texts=[(FIXTURES / "stock_fractional_sheet.txt").read_text()],
        )
    )
    operation.notes[0].operations[0].title = "BOA SAFRA ON NM @"
    operation.notes[0].operations[0].asset = "BOA"

    summary = summarize_payload(operation)

    assert 'BOA SAFRA | $105.82 / 22 = $4.81 (1 operations, side=buy, market="FRACIONARIO", dc=debit, allocated_costs=$0.02)' in summary


def test_summary_separates_batch_files():
    sheet = (FIXTURES / "stock_fractional_sheet.txt").read_text()
    parser = ClearParser()
    first = parser.parse(
        ExtractedPdf(source_file=Path("first.pdf"), text=sheet, pages=1, page_texts=[sheet])
    )
    second = parser.parse(
        ExtractedPdf(source_file=Path("second.pdf"), text=sheet, pages=1, page_texts=[sheet])
    )

    summary = summarize_payload(BatchResult(results=[first, second]))

    assert 'File: "first.pdf"' in summary
    assert 'File: "second.pdf"' in summary
    assert 'File: "first.pdf"' in summary.split("\n\n----------------------------------------\n")[0]
    assert 'File: "second.pdf"' in summary.split("\n\n----------------------------------------\n")[1]
    assert summary.count("\n\n----------------------------------------\n") == 1


def test_summary_assigns_rounding_remainder_to_largest_asset():
    parsed = BrokerageFile(
        broker=BrokerInfo(name="Test Broker"),
        source_file="sample.pdf",
        pages=1,
        notes=[
            NegotiationNote(
                number="1",
                sheet_count=1,
                pdf_pages=[1],
                financial_summary={"settlement_fee": Decimal("0.04")},
                operations=[
                    Operation(raw="", asset="AAA", title="AAA ON", quantity=Decimal("1"), total=Decimal("11"), side="buy", market="VISTA", debit_credit="debit"),
                    Operation(raw="", asset="BBB", title="BBB ON", quantity=Decimal("1"), total=Decimal("10"), side="buy", market="VISTA", debit_credit="debit"),
                    Operation(raw="", asset="CCC", title="CCC ON", quantity=Decimal("1"), total=Decimal("10"), side="buy", market="VISTA", debit_credit="debit"),
                ],
            )
        ],
    )

    summary = summarize_payload(parsed)

    assert 'AAA | $11.00 / 1 = $11.00 (1 operations, side=buy, market="VISTA", dc=debit, allocated_costs=$0.02)' in summary
    assert 'BBB | $10.00 / 1 = $10.00 (1 operations, side=buy, market="VISTA", dc=debit, allocated_costs=$0.01)' in summary
    assert 'CCC | $10.00 / 1 = $10.00 (1 operations, side=buy, market="VISTA", dc=debit, allocated_costs=$0.01)' in summary


def test_summary_supports_cm_capital_option_strike_and_costs():
    sheet = (Path(__file__).parent / "fixtures" / "cm_capital" / "options_sale_sheet.txt").read_text()
    parsed = CmCapitalParser().parse(
        ExtractedPdf(source_file=Path("sample.pdf"), text=sheet, pages=1, page_texts=[sheet])
    )

    summary = summarize_payload(parsed)

    assert "Broker: CM Capital" in summary
    assert "Financial: irrf=$0.00 | settlement_fee=$0.01 | emoluments=$0.02 | operational_fee=$0.00 | registration_fee=$0.04 | allocated_costs=$0.07" in summary
    assert 'ABCDO879 | $60.00 / 500 = $0.12 (1 operations, side=sell, market="OPCAO DE VENDA", dc=credit, allocated_costs=$0.07, strike=$8.37)' in summary
