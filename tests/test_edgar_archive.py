"""Historical Form 4 harvesting from EDGAR's quarterly index.

The risks here are volume and silence: a quarter holds ~60,000 Form 4s,
so the CIK filter has to actually bite before anything downloads, and a
filing that yields no signal has to be distinguishable from one that
failed. Both are pinned below.
"""

import xml.etree.ElementTree as ET
from datetime import date

import pytest
import requests

from topos.collectors.edgar_archive import (
    EdgarArchiveCollector,
    EdgarUnavailable,
    IndexEntry,
    extract_ownership_xml,
    parse_master_index,
)

MASTER_IDX = """Description:           Master Index of EDGAR Dissemination Feed
Last Data Received:    March 31, 2024

CIK|Company Name|Form Type|Date Filed|Filename
--------------------------------------------------------------------------------
320193|Apple Inc.|4|2024-01-05|edgar/data/320193/0000320193-24-000006.txt
320193|Apple Inc.|10-K|2024-02-01|edgar/data/320193/0000320193-24-000010.txt
789019|MICROSOFT CORP|4|2024-01-08|edgar/data/789019/0000789019-24-000021.txt
1018724|AMAZON COM INC|4|2024-02-14|edgar/data/1018724/0001018724-24-000044.txt
"""

# A Form 4 submission: SGML wrapper, the XML we want, and a rendered HTML
# copy alongside it — which is what makes slicing by element name safer
# than assuming document order.
SUBMISSION = b"""<SEC-DOCUMENT>0000320193-24-000006.txt : 20240105
<SEC-HEADER>ACCESSION NUMBER: 0000320193-24-000006
</SEC-HEADER>
<DOCUMENT>
<TYPE>4
<FILENAME>wk-form4.xml
<TEXT>
<XML>
<?xml version="1.0"?>
<ownershipDocument>
  <periodOfReport>2024-01-03</periodOfReport>
  <issuer>
    <issuerCik>0000320193</issuerCik>
    <issuerTradingSymbol>AAPL</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>COOK TIMOTHY</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isOfficer>1</isOfficer></reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2024-01-03</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>10000</value></transactionShares>
        <transactionPricePerShare><value>180.00</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
</XML>
</TEXT>
</DOCUMENT>
<DOCUMENT>
<TYPE>GRAPHIC
<TEXT>
<html><body>rendered copy, much larger, not what we want</body></html>
</TEXT>
</DOCUMENT>
</SEC-DOCUMENT>
"""

TICKER_MAP = b"""{"0":{"cik_str":320193,"ticker":"AAPL","title":"Apple Inc."},
"1":{"cik_str":789019,"ticker":"MSFT","title":"Microsoft"},
"2":{"cik_str":1018724,"ticker":"AMZN","title":"Amazon"}}"""


# --- index parsing ----------------------------------------------------


def test_index_keeps_only_the_requested_form_type():
    entries = parse_master_index(MASTER_IDX, form_type="4")

    assert [e.cik for e in entries] == [320193, 789019, 1018724]
    assert all(e.form_type == "4" for e in entries)


def test_index_headers_and_separators_are_not_read_as_filings():
    entries = parse_master_index(MASTER_IDX)

    assert all(isinstance(e.cik, int) for e in entries)
    assert len(entries) == 4  # three Form 4s plus the 10-K


def test_index_survives_a_malformed_row():
    broken = MASTER_IDX + "not|enough\n999|Bad Co|4|not-a-date|edgar/data/999/x.txt\n"

    entries = parse_master_index(broken, form_type="4")

    # The good rows survive; neither bad row appears.
    assert len(entries) == 3


def test_entry_derives_its_accession_and_url():
    entry = parse_master_index(MASTER_IDX, form_type="4")[0]

    assert entry.accession == "0000320193-24-000006"
    assert entry.url == (
        "https://www.sec.gov/Archives/edgar/data/320193/0000320193-24-000006.txt"
    )
    assert entry.filed == date(2024, 1, 5)


# --- pulling the XML out of a submission ------------------------------


def test_ownership_document_is_sliced_out_of_the_submission():
    root = extract_ownership_xml(SUBMISSION)

    assert root is not None
    assert root.tag == "ownershipDocument"
    assert root.findtext("issuer/issuerTradingSymbol") == "AAPL"


def test_a_submission_without_ownership_xml_returns_none():
    # A paper filing or an unexpected format — nothing to read, not a crash.
    assert extract_ownership_xml(b"<SEC-DOCUMENT>no xml here</SEC-DOCUMENT>") is None


def test_malformed_ownership_xml_returns_none_rather_than_raising():
    assert extract_ownership_xml(b"<ownershipDocument><unclosed></ownershipDocument>") is None


# --- fetching ---------------------------------------------------------


class _Response:
    def __init__(self, content=b"", status_code=200):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


class _Session:
    def __init__(self, routes, default_status=404):
        self.routes = routes
        self.default_status = default_status
        self.calls: list[str] = []
        self.headers: dict[str, str] = {}

    def get(self, url, timeout=0):
        self.calls.append(url)
        if url in self.routes:
            return self.routes[url]
        return _Response(status_code=self.default_status)


IDX_URL = "https://www.sec.gov/Archives/edgar/full-index/2024/QTR1/master.idx"
AAPL_URL = "https://www.sec.gov/Archives/edgar/data/320193/0000320193-24-000006.txt"
MSFT_URL = "https://www.sec.gov/Archives/edgar/data/789019/0000789019-24-000021.txt"
AMZN_URL = "https://www.sec.gov/Archives/edgar/data/1018724/0001018724-24-000044.txt"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


@pytest.fixture
def cache(tmp_path):
    return tmp_path / "edgar"


def _collector(cache, routes):
    return EdgarArchiveCollector(cache_dir=cache, delay=0, session=_Session(routes))


def test_the_cik_filter_prevents_downloading_the_whole_quarter(cache):
    # The point of the filter: 60,000 filings a quarter, and only the
    # companies we hold other data for are worth a request.
    session = _Session({IDX_URL: _Response(MASTER_IDX.encode()), AAPL_URL: _Response(SUBMISSION)})
    collector = EdgarArchiveCollector(cache_dir=cache, delay=0, session=session)

    result = collector.form4_signals(2024, 1, ciks={320193})

    assert result.filings_in_index == 3
    assert result.filings_matched == 1
    # Only the index and the one matching filing were ever requested.
    assert session.calls == [IDX_URL, AAPL_URL]


def test_signals_come_out_of_real_filing_xml(cache):
    collector = _collector(
        cache, {IDX_URL: _Response(MASTER_IDX.encode()), AAPL_URL: _Response(SUBMISSION)}
    )

    result = collector.form4_signals(2024, 1, ciks={320193})

    assert len(result.signals) == 1
    signal = result.signals[0]
    assert signal.ticker == "AAPL"
    assert signal.source == "sec_form4"
    # The insider's trade date, not the filing date two days later.
    assert signal.event_date == date(2024, 1, 3)
    assert signal.evidence["direction"] == "buy"


def test_extracted_xml_is_cached_so_a_rerun_refetches_nothing(cache):
    session = _Session({IDX_URL: _Response(MASTER_IDX.encode()), AAPL_URL: _Response(SUBMISSION)})
    collector = EdgarArchiveCollector(cache_dir=cache, delay=0, session=session)

    collector.form4_signals(2024, 1, ciks={320193})
    calls_after_first = len(session.calls)
    collector.form4_signals(2024, 1, ciks={320193})

    assert len(session.calls) == calls_after_first


def test_one_missing_filing_does_not_abort_the_quarter(cache):
    collector = _collector(
        cache,
        {
            IDX_URL: _Response(MASTER_IDX.encode()),
            AAPL_URL: _Response(SUBMISSION),
            # MSFT is absent -> 404
        },
    )

    result = collector.form4_signals(2024, 1, ciks={320193, 789019})

    assert result.filings_matched == 2
    assert result.filings_fetched == 1
    assert len(result.failures) == 1
    assert len(result.signals) == 1


def test_a_filing_with_no_ownership_xml_is_counted_but_not_a_failure(cache):
    collector = _collector(
        cache,
        {
            IDX_URL: _Response(MASTER_IDX.encode()),
            AAPL_URL: _Response(b"<SEC-DOCUMENT>paper filing, no xml</SEC-DOCUMENT>"),
        },
    )

    result = collector.form4_signals(2024, 1, ciks={320193})

    assert result.filings_fetched == 1
    assert result.filings_parsed == 0
    assert result.failures == []
    assert result.signals == []


def test_tickers_resolve_to_ciks_through_secs_own_map(cache):
    collector = _collector(cache, {TICKERS_URL: _Response(TICKER_MAP)})

    assert collector.ciks_for(["AAPL", "msft", "NOTREAL"]) == {320193, 789019}


def test_being_blocked_points_at_the_user_agent(cache):
    # Public SEC archives need no credentials; a 403 means the client was
    # filtered, which retrying will not fix.
    session = _Session({}, default_status=403)
    collector = EdgarArchiveCollector(cache_dir=cache, delay=0, session=session)

    with pytest.raises(EdgarUnavailable, match="SEC_EDGAR_USER_AGENT"):
        collector.index(2024, 1)


def test_a_quarter_that_does_not_exist_is_reported_as_such(cache):
    collector = _collector(cache, {})

    with pytest.raises(EdgarUnavailable, match="Not published"):
        collector.index(2099, 1)


# --- quarter enumeration ----------------------------------------------


def test_quarters_span_year_boundaries():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from backfill_form4 import quarters_between

    assert quarters_between(date(2024, 11, 15), date(2025, 2, 1)) == [(2024, 4), (2025, 1)]


def test_a_range_inside_one_quarter_yields_that_quarter():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from backfill_form4 import quarters_between

    # Not an empty list: the quarter in progress holds filings already.
    assert quarters_between(date(2026, 8, 1), date(2026, 8, 6)) == [(2026, 3)]


def test_every_quarter_in_a_multi_year_range_is_covered():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from backfill_form4 import quarters_between

    quarters = quarters_between(date(2024, 1, 1), date(2026, 8, 6))

    assert quarters[0] == (2024, 1)
    assert quarters[-1] == (2026, 3)
    assert len(quarters) == 11
