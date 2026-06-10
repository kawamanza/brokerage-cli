from pathlib import Path

from brokerage.brokers.clear import ClearParser
from brokerage.models import BrokerNoteType, ExtractedPdf

FIXTURES = Path(__file__).parent / "fixtures" / "clear"
STOCK_SHEET = (FIXTURES / "stock_fractional_sheet.txt").read_text()
OPTION_PUT_SHEET = (FIXTURES / "put_option_sheet.txt").read_text()


def test_clear_parser_groups_sheets_by_note_number():
    parser = ClearParser()

    parsed = parser.parse(
        ExtractedPdf(
            source_file=Path("sample.pdf"),
            text=f"{STOCK_SHEET}\n{OPTION_PUT_SHEET}",
            pages=2,
            page_texts=[STOCK_SHEET, OPTION_PUT_SHEET],
            used_password=True,
        )
    )

    assert parsed.broker.name == "Clear"
    assert parsed.layout_version == "clear-note-negotiation-v1"
    assert parsed.pages == 2
    assert parsed.used_password is True
    assert parsed.customer.code == "99999999"
    assert parsed.customer.name == "CLIENTE TESTE"
    assert len(parsed.notes) == 2
    assert parsed.notes[0].number == "100000001"
    assert parsed.notes[0].sheet_count == 1
    assert parsed.notes[0].pdf_pages == [1]
    assert parsed.notes[0].broker_note_type == BrokerNoteType.STOCKS
    assert parsed.notes[0].assets == ["ABCD"]
    assert parsed.notes[0].operations[0].side == "buy"
    assert str(parsed.notes[0].operations[0].quantity) == "22"
    assert str(parsed.notes[0].operations[0].price) == "4.81"
    assert str(parsed.notes[0].operations[0].total) == "105.82"
    assert parsed.notes[0].financial_summary["settlement_date"] == "29/07/2025"


def test_clear_parser_aggregates_multiple_sheets_for_same_note():
    parser = ClearParser()
    second_sheet_same_note = STOCK_SHEET.replace("Folha\n1", "Folha\n2")

    parsed = parser.parse(
        ExtractedPdf(
            source_file=Path("sample.pdf"),
            text=f"{STOCK_SHEET}\n{second_sheet_same_note}",
            pages=2,
            page_texts=[STOCK_SHEET, second_sheet_same_note],
        )
    )

    assert len(parsed.notes) == 1
    assert parsed.notes[0].number == "100000001"
    assert parsed.notes[0].sheet_count == 2
    assert parsed.notes[0].pdf_pages == [1, 2]
    assert len(parsed.notes[0].operations) == 2


def test_clear_parser_supports_put_options_layout_shape():
    parser = ClearParser()

    parsed = parser.parse(
        ExtractedPdf(
            source_file=Path("sample.pdf"),
            text=OPTION_PUT_SHEET,
            pages=1,
            page_texts=[OPTION_PUT_SHEET],
        )
    )

    note = parsed.notes[0]
    operation = note.operations[0]

    assert note.broker_note_type == BrokerNoteType.OPTIONS
    assert note.assets == ["ABCDH123"]
    assert operation.market == "OPCAO DE VENDA"
    assert operation.term == "06/26"
    assert operation.asset == "ABCDH123"
    assert str(operation.strike) == "1.23"
    assert operation.side == "sell"
    assert str(operation.quantity) == "300"
    assert str(operation.price) == "0.12"
    assert str(operation.total) == "36.00"
    assert note.business_summary["options_sales"] == operation.total
    assert note.financial_summary["settlement_date"] == "10/06/2026"


def test_clear_parser_supports_multiple_operations_in_same_sheet():
    parser = ClearParser()
    sheet = (FIXTURES / "multiple_options_sheet.txt").read_text()

    parsed = parser.parse(
        ExtractedPdf(
            source_file=Path("sample.pdf"),
            text=sheet,
            pages=1,
            page_texts=[sheet],
        )
    )

    note = parsed.notes[0]
    operations = note.operations

    assert note.number == "100000003"
    assert note.broker_note_type == BrokerNoteType.OPTIONS
    assert len(operations) == 5
    assert [operation.asset for operation in operations] == [
        "WXYZQ810E",
        "ABCDH19",
        "ABCDH19",
        "ABCDH19",
        "ABCDQ150W4",
    ]
    assert [str(operation.quantity) for operation in operations] == ["200", "700", "100", "100", "3000"]
    assert [str(operation.total) for operation in operations] == ["1620.00", "42.00", "6.00", "6.00", "60.00"]
    assert operations[0].market == "EXERC OPC"
    assert operations[0].term == "05/26"
    assert operations[0].observation.startswith("exercise_side=sell")
    assert operations[1].strike == operations[2].strike == operations[3].strike
    assert str(operations[1].strike) == "1.90"
    assert str(operations[4].strike) == "1.50"
    assert note.computed["operation_count"] == 5
