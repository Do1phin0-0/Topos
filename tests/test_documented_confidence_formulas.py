"""Pins the confidence formulas transcribed in docs/DATA_LINEAGE.md.

The lineage document claims specific formulas per source. A document that
silently drifts from the code is worse than none, so each documented
formula is asserted here against the real extractor. If a weight changes,
this fails and the doc has to be updated with it.
"""

import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

import pytest

from topos.collectors.prices import Bar
from topos.signals.congress import extract_congress_signal
from topos.signals.form4 import extract_form4_signal
from topos.signals.news import NewsSignalExtractor
from topos.signals.technical import TechnicalSignalExtractor

_FORM4 = """<?xml version="1.0"?>
<ownershipDocument>
  <issuer><issuerTradingSymbol>ACME</issuerTradingSymbol></issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>Jane Doe</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isOfficer>{officer}</isOfficer><isDirector>0</isDirector></reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-07-15</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>{shares}</value></transactionShares>
        <transactionPricePerShare><value>{price}</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


def _form4(officer: int, shares: float, price: float):
    return extract_form4_signal(
        ET.fromstring(_FORM4.format(officer=officer, shares=shares, price=price)),
        "https://example.com/f-index.htm",
    )


@pytest.mark.parametrize(
    "officer,shares,price,expected",
    [
        # doc: 0.2 + role_weight + min(value/1M, 1)*0.5
        # officer, $1M+  -> 0.2 + 0.3 + 0.5 = 1.0
        (1, 10_000, 100.0, 1.0),
        # officer, $500k -> 0.2 + 0.3 + 0.25 = 0.75
        (1, 5_000, 100.0, 0.75),
        # non-insider, $500k -> 0.2 + 0.15 + 0.25 = 0.60
        (0, 5_000, 100.0, 0.60),
        # non-insider, tiny -> 0.2 + 0.15 + ~0 = 0.35
        (0, 1, 1.0, 0.35),
    ],
)
def test_form4_confidence_matches_documented_formula(officer, shares, price, expected):
    assert _form4(officer, shares, price).confidence == pytest.approx(expected, abs=0.001)


@pytest.mark.parametrize(
    "amount,expected",
    [
        # doc: 0.25 + min(midpoint/250_000, 1)*0.4
        # midpoint 175,000.5 -> 0.25 + 0.7*0.4 = 0.53
        ("$100,001 - $250,000", 0.53),
        # midpoint 8,000.5 -> 0.25 + 0.032*0.4 = 0.263
        ("$1,001 - $15,000", 0.263),
        # midpoint above 250k caps -> 0.25 + 0.4 = 0.65
        ("$500,001 - $1,000,000", 0.65),
    ],
)
def test_congress_confidence_matches_documented_formula(amount, expected):
    signal = extract_congress_signal(
        {
            "ticker": "ACME",
            "type": "purchase",
            "amount": amount,
            "representative": "Jane Rep",
            "chamber": "house",
            "transaction_date": "2026-07-15",
        }
    )

    assert signal.confidence == pytest.approx(expected, abs=0.002)


def test_earnings_confidence_is_the_documented_fixed_value():
    from unittest.mock import MagicMock

    from topos.signals.earnings import EarningsSignalExtractor

    collector = MagicMock()
    collector.latest_filings.return_value = [
        {
            "index_url": "https://sec.gov/Archives/edgar/data/1/a-index.htm",
            "cik": 1,
            "filed_at": "2026-08-01T14:31:02-04:00",
        }
    ]
    collector.ticker_for_cik.return_value = "ACME"
    collector.fetch_text.return_value = "Item 2.02 Results of Operations"

    [signal] = EarningsSignalExtractor(collector=collector).extract(limit=1)

    # doc: fixed 0.4, not size- or content-aware
    assert signal.confidence == 0.4


def test_institutional_confidence_matches_documented_formula():
    from unittest.mock import MagicMock

    from topos.signals.institutional import InstitutionalSignalExtractor

    extractor = InstitutionalSignalExtractor(collector=MagicMock(), figi=MagicMock())

    # doc: 0.3 + min(pct_change, 1)*0.5, only when pct_change >= 0.10
    increases = extractor._diff(
        {"111": {"shares": 1000.0, "issuer": "X"}},
        {"111": {"shares": 1500.0, "issuer": "X"}},  # +50%
    )
    assert increases["111"]["confidence"] == pytest.approx(0.3 + 0.5 * 0.5, abs=0.001)

    # Below the 10% threshold, nothing is emitted at all.
    assert extractor._diff(
        {"222": {"shares": 1000.0, "issuer": "Y"}},
        {"222": {"shares": 1050.0, "issuer": "Y"}},  # +5%
    ) == {}


def test_news_confidence_matches_documented_formula():
    headlines = [
        {"title": "Company smashes earnings, stock soars on record profit",
         "pub_date": "Wed, 15 Jul 2026 10:00:00 GMT"},
    ]

    signal = NewsSignalExtractor()._score("ACME", headlines)

    # doc: 0.2 + |mean_compound|*0.6 + min(count/20, 0.2)
    mean = signal.evidence["avg_compound"]
    expected = 0.2 + abs(mean) * 0.6 + min(len(headlines) / 20, 0.2)
    assert signal.confidence == pytest.approx(expected, abs=0.002)


def test_technical_confidence_matches_documented_formula():
    # A pure downtrend pins RSI at 0 -> fully oversold -> strength 1.0
    closes = [200.0 - i for i in range(60)]
    bars = [
        Bar(date=date(2026, 6, 1) + timedelta(days=i), open=c, high=c, low=c, close=c, volume=1e6)
        for i, c in enumerate(closes)
    ]

    signal = TechnicalSignalExtractor()._score("ACME", closes, as_of=bars[-1].date)

    # doc: 0.2 + min(strength, 1)*0.5 -> 0.2 + 0.5 = 0.7 at full strength
    assert signal.evidence["rsi_14"] == 0.0
    assert signal.confidence == pytest.approx(0.7, abs=0.001)
