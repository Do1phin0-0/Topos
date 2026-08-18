from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from topos.db.models import Base
from topos.signals.filing_13f import Filing13FSignalExtractor

PRIMARY_DOC_TEMPLATE = """
<edgarSubmission xmlns="http://www.sec.gov/edgar/thirteenffiler">
  <headerData>
    <filerInfo>
      <filer><credentials><cik>0001234567</cik></credentials></filer>
      <periodOfReport>{period}</periodOfReport>
    </filerInfo>
  </headerData>
  <formData>
    <coverPage><filingManager><name>Some Fund LLC</name></filingManager></coverPage>
  </formData>
</edgarSubmission>
"""

INFO_TABLE_TEMPLATE = """
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <cusip>037833100</cusip>
    <value>{apple_value}</value>
    <shrsOrPrnAmt><sshPrnamt>{apple_shares}</sshPrnamt></shrsOrPrnAmt>
  </infoTable>
  {extra}
</informationTable>
"""

TESLA_ROW = """
  <infoTable>
    <nameOfIssuer>TESLA INC</nameOfIssuer>
    <cusip>88160R101</cusip>
    <value>50000</value>
    <shrsOrPrnAmt><sshPrnamt>200</sshPrnamt></shrsOrPrnAmt>
  </infoTable>
"""


class FakeCollector:
    """Serves a canned filing per (call count) so successive extract()
    calls simulate successive quarters, without touching the network."""

    def __init__(self, filings_by_call: list[dict]) -> None:
        self._filings_by_call = filings_by_call
        self.call_index = 0

    def company_tickers(self):
        return [{"title": "Apple Inc.", "ticker": "AAPL"}, {"title": "Tesla Inc.", "ticker": "TSLA"}]

    def latest_filings(self, form_type, count=20):
        filing = self._filings_by_call[self.call_index]
        self.call_index += 1
        return [{"form_type": form_type, "title": "t", "index_url": "https://example.com/f/0001", "filed_at": "now"}]

    def filing_documents(self, index_url):
        return ["https://example.com/f/0001/primary_doc.xml", "https://example.com/f/0001/infoTable.xml"]

    def fetch_xml(self, url):
        import xml.etree.ElementTree as ET

        filing = self._filings_by_call[self.call_index - 1]
        if "primary_doc" in url:
            return ET.fromstring(PRIMARY_DOC_TEMPLATE.format(period=filing["period"]))
        return ET.fromstring(
            INFO_TABLE_TEMPLATE.format(
                apple_value=filing["apple_value"], apple_shares=filing["apple_shares"], extra=filing["extra"]
            )
        )


def _session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    def _get_session():
        return factory()

    return _get_session


def test_first_filing_establishes_baseline_with_no_signals():
    session_factory = _session_factory()
    collector = FakeCollector([{"period": "03-31-2026", "apple_value": 100_000, "apple_shares": 1000, "extra": ""}])

    signals = Filing13FSignalExtractor(collector=collector, session_factory=session_factory).extract()

    assert signals == []


def test_second_quarter_diffs_against_stored_baseline():
    session_factory = _session_factory()
    filings = [
        {"period": "03-31-2026", "apple_value": 100_000, "apple_shares": 1000, "extra": ""},
        {"period": "06-30-2026", "apple_value": 150_000, "apple_shares": 1500, "extra": TESLA_ROW},
    ]
    collector = FakeCollector(filings)
    extractor = Filing13FSignalExtractor(collector=collector, session_factory=session_factory)

    extractor.extract()  # baseline quarter
    signals = extractor.extract()  # second quarter: Apple increased, Tesla new

    by_ticker = {s.ticker: s for s in signals}
    assert by_ticker["AAPL"].evidence["change_type"] == "increased"
    assert by_ticker["AAPL"].evidence["direction"] == "buy"
    assert by_ticker["TSLA"].evidence["change_type"] == "new_position"


def test_reprocessing_same_period_is_a_noop():
    session_factory = _session_factory()
    filings = [
        {"period": "03-31-2026", "apple_value": 100_000, "apple_shares": 1000, "extra": ""},
        {"period": "03-31-2026", "apple_value": 100_000, "apple_shares": 1000, "extra": ""},
    ]
    collector = FakeCollector(filings)
    extractor = Filing13FSignalExtractor(collector=collector, session_factory=session_factory)

    extractor.extract()
    signals = extractor.extract()

    assert signals == []
