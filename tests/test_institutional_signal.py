import xml.etree.ElementTree as ET
from unittest.mock import MagicMock

from topos.signals.institutional import InstitutionalSignalExtractor, _parse_holdings, _strip_namespaces

_INFO_TABLE_XML = """<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>Acme Corp</nameOfIssuer>
    <cusip>000000001</cusip>
    <shrsOrPrnAmt><sshPrnAmt>10000</sshPrnAmt></shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>Widget Inc</nameOfIssuer>
    <cusip>000000002</cusip>
    <shrsOrPrnAmt><sshPrnAmt>500</sshPrnAmt></shrsOrPrnAmt>
  </infoTable>
</informationTable>"""


def test_strip_namespaces_and_parse_holdings():
    root = _strip_namespaces(ET.fromstring(_INFO_TABLE_XML))

    assert root.tag == "informationTable"
    holdings = _parse_holdings(root)
    assert holdings["000000001"] == {"shares": 10000.0, "issuer": "Acme Corp"}
    assert holdings["000000002"] == {"shares": 500.0, "issuer": "Widget Inc"}


def test_diff_flags_increases_and_new_positions_above_threshold():
    extractor = InstitutionalSignalExtractor(collector=MagicMock(), figi=MagicMock())

    prior = {
        "111": {"shares": 1000.0, "issuer": "Grew A Lot"},
        "222": {"shares": 1000.0, "issuer": "Barely Moved"},
    }
    current = {
        "111": {"shares": 1500.0, "issuer": "Grew A Lot"},  # +50%, above threshold
        "222": {"shares": 1020.0, "issuer": "Barely Moved"},  # +2%, below threshold
        "333": {"shares": 200.0, "issuer": "Brand New"},  # new position
    }

    increases = extractor._diff(prior, current)

    assert set(increases.keys()) == {"111", "333"}
    assert increases["111"]["pct_change"] == 0.5
    assert increases["333"]["pct_change"] == 1.0
    assert increases["333"]["shares_prior"] == 0.0


def test_extract_for_filer_resolves_cusips_to_tickers_and_skips_unresolved():
    mock_collector = MagicMock()
    mock_figi = MagicMock()

    current_filing = {"index_url": "https://sec.gov/cur-index.htm", "filed_at": "2026-08-01T14:31:02-04:00"}
    prior_filing = {"index_url": "https://sec.gov/prior-index.htm", "filing_date": "2026-05-01"}

    extractor = InstitutionalSignalExtractor(collector=mock_collector, figi=mock_figi)
    extractor._holdings_for_filing = MagicMock(
        side_effect=lambda url: (
            {"111": {"shares": 1500.0, "issuer": "Grew A Lot"}, "999": {"shares": 300.0, "issuer": "No Ticker Co"}}
            if url == current_filing["index_url"]
            else {"111": {"shares": 1000.0, "issuer": "Grew A Lot"}}
        )
    )
    extractor._find_prior_13f = MagicMock(return_value=prior_filing)
    mock_figi.cusips_to_tickers.return_value = {"111": "ACME"}  # "999" deliberately unresolved

    signals = extractor._extract_for_filer(cik=12345, current_filing=current_filing)

    assert len(signals) == 1
    assert signals[0].ticker == "ACME"
    assert signals[0].source == "institutional_13f"
    assert signals[0].evidence["direction"] == "buy"
    assert signals[0].evidence["pct_change"] == 0.5


def test_extract_returns_empty_when_no_prior_filing_exists():
    mock_collector = MagicMock()
    mock_figi = MagicMock()
    extractor = InstitutionalSignalExtractor(collector=mock_collector, figi=mock_figi)
    extractor._holdings_for_filing = MagicMock(return_value={"111": {"shares": 100.0, "issuer": "X"}})
    extractor._find_prior_13f = MagicMock(return_value=None)

    signals = extractor._extract_for_filer(cik=1, current_filing={"index_url": "https://sec.gov/a-index.htm", "filed_at": "2026-08-01T14:31:02-04:00"})

    assert signals == []
    mock_figi.cusips_to_tickers.assert_not_called()
