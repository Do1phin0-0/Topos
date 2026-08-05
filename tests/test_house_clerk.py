"""The House Clerk replacement for the withdrawn Stock Watcher mirror.

The parser is the risky part: PTR layouts vary between filings, amount
ranges wrap across lines, and a row read wrong produces a transaction
that never happened. These fixtures reproduce the layouts as pdfplumber
actually emits them — including the wrapping — rather than a tidied
version that would let a fragile parser pass.
"""

import zipfile
from datetime import date
from io import BytesIO

import pytest

from topos.collectors.house_clerk import (
    FilingRef,
    HouseClerkCollector,
    HouseClerkUnavailable,
    parse_index,
)
from topos.collectors.ptr_parser import parse_transactions
from topos.signals.congress import extract_congress_signal

# As pdfplumber emits it: the header is split across lines, and the
# amount range wraps onto the following line.
ELECTRONIC_PTR = """
                                    PERIODIC TRANSACTION REPORT

ID     Owner  Asset                    Transaction  Date        Notification  Amount
                                       Type                     Date
SP            Apple Inc. (AAPL) [ST]   P            01/02/2024  01/15/2024    $1,001 -
                                                                              $15,000
              Microsoft Corp (MSFT)    S            02/14/2024  02/20/2024    $250,001 -
              [ST]                                                            $500,000
JT            Vanguard 500 Index (VFIAX) [MF]  P    03/01/2024  03/10/2024    $15,001 -
                                                                              $50,000
"""

INDEX_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<FinancialDisclosure>
  <Member>
    <Prefix>Hon.</Prefix><Last>Doe</Last><First>Jane</First><Suffix></Suffix>
    <FilingType>P</FilingType><StateDst>TX07</StateDst>
    <Year>2024</Year><FilingDate>1/20/2024</FilingDate><DocID>20024001</DocID>
  </Member>
  <Member>
    <Prefix>Hon.</Prefix><Last>Roe</Last><First>Richard</First><Suffix></Suffix>
    <FilingType>O</FilingType><StateDst>CA11</StateDst>
    <Year>2024</Year><FilingDate>5/15/2024</FilingDate><DocID>20024002</DocID>
  </Member>
  <Member>
    <Prefix>Hon.</Prefix><Last>Poe</Last><First>Mary</First><Suffix></Suffix>
    <FilingType>P</FilingType><StateDst>NY03</StateDst>
    <Year>2024</Year><FilingDate>7/01/2024</FilingDate><DocID>20024003</DocID>
  </Member>
</FinancialDisclosure>
"""


# --- parsing transactions --------------------------------------------


def test_reads_transactions_whose_amount_wraps_across_lines():
    records = parse_transactions(ELECTRONIC_PTR, member="Jane Doe")

    by_ticker = {r["ticker"]: r for r in records}
    assert set(by_ticker) == {"AAPL", "MSFT"}  # the index fund is excluded

    apple = by_ticker["AAPL"]
    assert apple["type"] == "purchase"
    assert apple["transaction_date"] == "2024-01-02"
    assert apple["disclosure_date"] == "2024-01-15"
    assert apple["amount"] == "$1,001 - $15,000"
    assert apple["representative"] == "Jane Doe"
    assert apple["chamber"] == "house"


def test_the_first_date_is_the_trade_not_the_notification():
    # Column order is transaction date then notification date. Reversing
    # them would shift every forward return by the disclosure lag, which
    # is the exact bug this project already fixed once.
    records = parse_transactions(ELECTRONIC_PTR, member="Jane Doe")
    apple = next(r for r in records if r["ticker"] == "AAPL")

    assert apple["transaction_date"] < apple["disclosure_date"]


def test_sales_are_read_as_sales():
    records = parse_transactions(ELECTRONIC_PTR, member="Jane Doe")
    msft = next(r for r in records if r["ticker"] == "MSFT")

    assert msft["type"] == "sale"
    assert msft["amount"] == "$250,001 - $500,000"


def test_fund_holdings_are_excluded():
    # Buying an index fund is not a view on a company.
    records = parse_transactions(ELECTRONIC_PTR, member="Jane Doe")

    assert not any(r["ticker"] == "VFIAX" for r in records)


def test_partial_sales_are_flagged_and_still_read_as_sales():
    text = "Tesla Inc (TSLA) [ST] S (partial) 04/03/2024 04/20/2024 $1,001 - $15,000"

    record = parse_transactions(text, member="Jane Doe")[0]

    assert record["type"] == "sale"
    assert record["partial"] is True


def test_the_top_amount_bracket_is_recognised():
    text = "Nvidia Corp (NVDA) [ST] P 05/06/2024 05/20/2024 Over $50,000,000"

    record = parse_transactions(text, member="Jane Doe")[0]

    assert record["amount"] == "Over $50,000,000"


def test_a_scan_with_no_text_yields_nothing_rather_than_a_guess():
    assert parse_transactions("", member="Jane Doe") == []
    assert parse_transactions("  \n \n ", member="Jane Doe") == []


def test_rows_missing_a_date_are_dropped_not_defaulted():
    # An undated transaction cannot anchor a forward return, so it must
    # not survive with today's date standing in for the real one.
    text = "Apple Inc. (AAPL) [ST] P $1,001 - $15,000"

    assert parse_transactions(text, member="Jane Doe") == []


def test_a_letter_inside_the_company_name_is_not_read_as_the_type():
    # "U.S. Bancorp" contains a standalone-looking S. Reading it as the
    # transaction type would turn a purchase into a sale — a signal
    # pointing the wrong way, which is worse than a missing one.
    text = "U.S. Bancorp (USB) [ST] P 01/02/2024 01/15/2024 $1,001 - $15,000"

    record = parse_transactions(text, member="Jane Doe")[0]

    assert record["type"] == "purchase"


def test_a_ticker_that_wraps_onto_the_next_line_is_still_found():
    # Long asset names wrap, and the ticker sits at the end of the name,
    # so it lands below the line carrying the dates.
    text = (
        "  Some Very Long Company Name Incorporated    P  01/02/2024  01/15/2024  $1,001 -\n"
        "  Class A Common Stock (SVLCN) [ST]                                       $15,000\n"
    )

    records = parse_transactions(text, member="Jane Doe")

    assert len(records) == 1
    assert records[0]["ticker"] == "SVLCN"
    assert records[0]["amount"] == "$1,001 - $15,000"


def test_a_row_with_no_readable_type_is_dropped():
    # Direction is the whole point of the signal; without it there is
    # nothing to be right or wrong about.
    text = "Apple Inc. (AAPL) [ST] 01/02/2024 01/15/2024 $1,001 - $15,000"

    assert parse_transactions(text, member="Jane Doe") == []


def test_asset_types_without_a_bracket_are_kept():
    # Not every filing includes the type code; dropping those would lose
    # real disclosures.
    text = "Apple Inc. (AAPL) P 01/02/2024 01/15/2024 $1,001 - $15,000"

    records = parse_transactions(text, member="Jane Doe")

    assert len(records) == 1
    assert records[0]["asset_type"] is None


# --- the records still feed the existing extractor --------------------


def test_parsed_records_flow_through_the_existing_signal_extractor():
    records = parse_transactions(
        ELECTRONIC_PTR, member="Jane Doe", ptr_link="https://example.gov/1.pdf"
    )

    signals = [s for s in (extract_congress_signal(r) for r in records) if s]

    assert {s.ticker for s in signals} == {"AAPL", "MSFT"}
    apple = next(s for s in signals if s.ticker == "AAPL")
    assert apple.source == "congress_house"
    assert apple.event_date == date(2024, 1, 2)
    assert apple.evidence["direction"] == "buy"
    assert "Jane Doe" in apple.dedup_key


def test_the_same_filing_parsed_twice_produces_identical_dedup_keys():
    # Re-running a year must not re-insert every transaction.
    first = parse_transactions(ELECTRONIC_PTR, member="Jane Doe")
    second = parse_transactions(ELECTRONIC_PTR, member="Jane Doe")

    keys = lambda rows: {  # noqa: E731
        s.dedup_key for s in (extract_congress_signal(r) for r in rows) if s
    }
    assert keys(first) == keys(second)


# --- the filing index -------------------------------------------------


def test_index_keeps_transaction_reports_and_drops_annual_filings():
    filings = parse_index(INDEX_XML)

    assert [f.doc_id for f in filings] == ["20024001", "20024003"]
    assert filings[0].member == "Jane Doe"
    assert filings[0].year == 2024
    assert filings[0].pdf_url.endswith("/ptr-pdfs/2024/20024001.pdf")


def test_index_survives_a_filing_with_missing_fields():
    xml = b"""<FinancialDisclosure><Member>
        <FilingType>P</FilingType><DocID>20024009</DocID><Year>2024</Year>
    </Member></FinancialDisclosure>"""

    filings = parse_index(xml)

    assert len(filings) == 1
    assert filings[0].member == "unknown"


def test_a_filing_with_no_doc_id_is_skipped():
    # Without a document id there is no PDF to fetch.
    xml = b"""<FinancialDisclosure><Member>
        <FilingType>P</FilingType><Last>Doe</Last><Year>2024</Year>
    </Member></FinancialDisclosure>"""

    assert parse_index(xml) == []


# --- fetching ---------------------------------------------------------


class _FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"unexpected status {self.status_code}")


class _FakeSession:
    def __init__(self, routes: dict[str, _FakeResponse]):
        self.routes = routes
        self.calls: list[str] = []
        self.headers: dict[str, str] = {}

    def get(self, url: str, timeout: int = 0) -> _FakeResponse:
        self.calls.append(url)
        if url not in self.routes:
            return _FakeResponse(b"", status_code=404)
        return self.routes[url]


def _zip_with(name: str, payload: bytes) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr(name, payload)
    return buffer.getvalue()


@pytest.fixture
def cache(tmp_path):
    return tmp_path / "house"


def test_index_is_read_out_of_the_yearly_zip(cache):
    url = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/2024FD.zip"
    session = _FakeSession({url: _FakeResponse(_zip_with("2024FD.xml", INDEX_XML))})

    filings = HouseClerkCollector(cache_dir=cache, delay=0, session=session).index(2024)

    assert [f.doc_id for f in filings] == ["20024001", "20024003"]


def test_downloads_are_cached_so_a_rerun_costs_nothing(cache):
    url = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/2024FD.zip"
    session = _FakeSession({url: _FakeResponse(_zip_with("2024FD.xml", INDEX_XML))})
    collector = HouseClerkCollector(cache_dir=cache, delay=0, session=session)

    collector.index(2024)
    collector.index(2024)

    assert len(session.calls) == 1


def test_a_zip_without_an_index_is_reported_not_silently_empty(cache):
    url = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/2024FD.zip"
    session = _FakeSession({url: _FakeResponse(_zip_with("readme.txt", b"hello"))})

    with pytest.raises(HouseClerkUnavailable, match="no XML index"):
        HouseClerkCollector(cache_dir=cache, delay=0, session=session).index(2024)


def test_one_missing_pdf_does_not_abort_the_year(cache, monkeypatch):
    zip_url = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/2024FD.zip"
    first = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2024/20024001.pdf"
    session = _FakeSession(
        {
            zip_url: _FakeResponse(_zip_with("2024FD.xml", INDEX_XML)),
            first: _FakeResponse(b"%PDF-1.4 fake"),
            # 20024003 is absent -> 404
        }
    )
    monkeypatch.setattr(
        "topos.collectors.house_clerk._text_of", lambda _: ELECTRONIC_PTR
    )

    result = HouseClerkCollector(cache_dir=cache, delay=0, session=session).transactions(2024)

    assert result.filings_indexed == 2
    assert result.filings_fetched == 1
    assert len(result.failures) == 1
    assert {r["ticker"] for r in result.transactions} == {"AAPL", "MSFT"}


def test_scanned_filings_are_counted_separately_from_failures(cache, monkeypatch):
    zip_url = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/2024FD.zip"
    session = _FakeSession(
        {
            zip_url: _FakeResponse(_zip_with("2024FD.xml", INDEX_XML)),
            "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2024/20024001.pdf":
                _FakeResponse(b"%PDF scan"),
            "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2024/20024003.pdf":
                _FakeResponse(b"%PDF text"),
        }
    )
    texts = {b"%PDF scan": "", b"%PDF text": ELECTRONIC_PTR}
    monkeypatch.setattr(
        "topos.collectors.house_clerk._text_of", lambda pdf: texts[pdf]
    )

    result = HouseClerkCollector(cache_dir=cache, delay=0, session=session).transactions(2024)

    # A scan is a known limitation of the source, not something that went
    # wrong — conflating the two would hide a real parser regression.
    assert result.filings_fetched == 2
    assert result.filings_with_text == 1
    assert result.failures == []
    assert result.parse_rate == 0.5


def test_parse_rate_is_none_rather_than_zero_when_nothing_was_fetched():
    from topos.collectors.house_clerk import BackfillResult

    assert BackfillResult(year=2024).parse_rate is None
