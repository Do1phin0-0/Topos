"""The one seam the other tests mock out: a real PDF, really extracted.

Everything else feeds the parser text directly, which is right — that is
where the logic lives. But it leaves `_text_of` unverified, and a
collector that extracts nothing from a valid PDF would report a 0% parse
rate that looks exactly like a year of scanned paper filings.

This builds a PDF laid out like a Periodic Transaction Report, runs it
through pdfplumber, and checks the transactions come out the far end.
"""

import pytest

from topos.collectors.house_clerk import _text_of
from topos.collectors.ptr_parser import parse_transactions

fpdf = pytest.importorskip("fpdf", reason="fpdf2 builds the fixture PDF")

# Column x-positions, roughly as the Clerk's template lays them out.
COLUMNS = [12, 30, 108, 132, 168]

HEADER = ["ID", "Asset", "Type", "Date", "Notification"]
ROWS = [
    ["SP", "Apple Inc. (AAPL) [ST]", "P", "01/02/2024", "01/15/2024"],
    ["", "Microsoft Corp (MSFT) [ST]", "S", "02/14/2024", "02/20/2024"],
    ["JT", "Vanguard 500 Index (VFIAX) [MF]", "P", "03/01/2024", "03/10/2024"],
]
# The amount column wraps in the real template, and that wrapping is the
# thing most likely to break extraction — so it is reproduced here.
AMOUNTS = [("$1,001 -", "$15,000"), ("$250,001 -", "$500,000"), ("$15,001 -", "$50,000")]


def _report_pdf() -> bytes:
    document = fpdf.FPDF()
    document.add_page()
    document.set_font("helvetica", size=8)

    document.set_xy(60, 15)
    document.cell(80, 6, "PERIODIC TRANSACTION REPORT")

    y = 30
    for x, label in zip(COLUMNS, HEADER):
        document.set_xy(x, y)
        document.cell(40, 5, label)
    document.set_xy(196, y)
    document.cell(20, 5, "Amount")

    y += 8
    for row, (amount_top, amount_wrapped) in zip(ROWS, AMOUNTS):
        for x, value in zip(COLUMNS, row):
            document.set_xy(x, y)
            document.cell(40, 5, value)
        document.set_xy(196, y)
        document.cell(20, 5, amount_top)
        document.set_xy(196, y + 4)
        document.cell(20, 5, amount_wrapped)
        y += 12

    return bytes(document.output())


def test_a_real_pdf_yields_transactions_through_the_whole_chain():
    text = _text_of(_report_pdf())

    assert text.strip(), "pdfplumber extracted nothing from a text-layer PDF"

    records = parse_transactions(text, member="Jane Doe")
    by_ticker = {r["ticker"]: r for r in records}

    assert set(by_ticker) == {"AAPL", "MSFT"}  # fund excluded
    assert by_ticker["AAPL"]["type"] == "purchase"
    assert by_ticker["AAPL"]["transaction_date"] == "2024-01-02"
    assert by_ticker["AAPL"]["disclosure_date"] == "2024-01-15"
    assert by_ticker["AAPL"]["amount"] == "$1,001 - $15,000"
    assert by_ticker["MSFT"]["type"] == "sale"
    assert by_ticker["MSFT"]["amount"] == "$250,001 - $500,000"


def test_a_scanned_report_extracts_no_text_rather_than_raising():
    # An image-only page is what a paper filing looks like. It must come
    # back empty so the collector can count it as a scan, not a failure.
    document = fpdf.FPDF()
    document.add_page()

    assert _text_of(bytes(document.output())).strip() == ""
