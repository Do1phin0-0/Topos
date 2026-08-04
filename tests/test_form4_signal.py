import xml.etree.ElementTree as ET
from unittest.mock import MagicMock

from topos.signals.form4 import Form4SignalExtractor, extract_form4_signal

_SAMPLE_XML = """<?xml version="1.0"?>
<ownershipDocument>
  <issuer><issuerTradingSymbol>ACME</issuerTradingSymbol></issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>Jane Doe</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isOfficer>1</isOfficer><isDirector>0</isDirector></reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>5000</value></transactionShares>
        <transactionPricePerShare><value>42.50</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


def test_extract_form4_signal_parses_buy():
    root = ET.fromstring(_SAMPLE_XML)

    signal = extract_form4_signal(root, "https://example.com/filing-index.htm")

    assert signal.ticker == "ACME"
    assert signal.evidence["direction"] == "buy"
    assert signal.evidence["total_value_usd"] == 5000 * 42.50


def test_extract_form4_signal_returns_none_without_ticker():
    root = ET.fromstring("<ownershipDocument><issuer></issuer></ownershipDocument>")

    assert extract_form4_signal(root, "https://example.com/filing-index.htm") is None


def test_extractor_skips_non_xml_documents_and_uses_dict_shape():
    mock_collector = MagicMock()
    mock_collector.latest_filings.return_value = [
        {"index_url": "https://sec.gov/Archives/edgar/data/1/a-index.htm"},
    ]
    mock_collector.filing_documents.return_value = [
        {"name": "a-index.htm", "url": "https://sec.gov/.../a-index.htm"},
        {"name": "primary_doc.xml", "url": "https://sec.gov/.../primary_doc.xml"},
    ]
    mock_collector.fetch_xml.return_value = ET.fromstring(_SAMPLE_XML)

    signals = Form4SignalExtractor(collector=mock_collector).extract(limit=5)

    assert len(signals) == 1
    assert signals[0].ticker == "ACME"
    mock_collector.fetch_xml.assert_called_once_with("https://sec.gov/.../primary_doc.xml")
