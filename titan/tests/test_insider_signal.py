import xml.etree.ElementTree as ET

from titan.app.signals.insider import normalize_form4_xml

_BUY_XML = """<?xml version="1.0"?>
<ownershipDocument>
  <issuer><issuerTradingSymbol>ACME</issuerTradingSymbol></issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>Jane Doe</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isOfficer>1</isOfficer><isDirector>0</isDirector></reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-07-15</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>5000</value></transactionShares>
        <transactionPricePerShare><value>42.50</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""

_SELL_XML = """<?xml version="1.0"?>
<ownershipDocument>
  <issuer><issuerTradingSymbol>WIDG</issuerTradingSymbol></issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>John Roe</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isOfficer>0</isOfficer><isDirector>1</isDirector></reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-07-16</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>10.00</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


def test_normalize_buy():
    root = ET.fromstring(_BUY_XML)

    normalized = normalize_form4_xml(root, "https://example.com/filing-index.htm")

    assert normalized["ticker"] == "ACME"
    assert normalized["direction"] == "buy"
    assert normalized["is_officer"] is True
    assert normalized["shares"] == 5000.0
    assert normalized["total_value_usd"] == 5000 * 42.50


def test_normalize_sell():
    root = ET.fromstring(_SELL_XML)

    normalized = normalize_form4_xml(root, "https://example.com/filing-index.htm")

    assert normalized["ticker"] == "WIDG"
    assert normalized["direction"] == "sell"
    assert normalized["is_director"] is True


def test_normalize_returns_none_without_ticker():
    root = ET.fromstring("<ownershipDocument><issuer></issuer></ownershipDocument>")

    assert normalize_form4_xml(root, "https://example.com/filing-index.htm") is None


def test_normalize_returns_none_with_no_transactions():
    root = ET.fromstring(
        "<ownershipDocument><issuer><issuerTradingSymbol>ACME</issuerTradingSymbol></issuer></ownershipDocument>"
    )

    assert normalize_form4_xml(root, "https://example.com/filing-index.htm") is None
