import xml.etree.ElementTree as ET
from datetime import date

from topos.signals.filing_13f import (
    _normalize_title,
    build_ticker_map,
    diff_to_signal,
    parse_holdings,
)

INFO_TABLE_XML = """
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <cusip>037833100</cusip>
    <value>123456</value>
    <shrsOrPrnAmt>
      <sshPrnamt>1000</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <cusip>037833100</cusip>
    <value>500</value>
    <shrsOrPrnAmt>
      <sshPrnamt>4</sshPrnamt>
    </shrsOrPrnAmt>
  </infoTable>
</informationTable>
"""


def test_normalize_title_strips_punctuation_and_suffixes():
    assert _normalize_title("Apple Inc.") == "APPLE"
    assert _normalize_title("MICROSOFT CORP") == "MICROSOFT"
    assert _normalize_title("Berkshire Hathaway Inc. Class B") == "BERKSHIRE HATHAWAY"


def test_build_ticker_map_uses_normalized_titles():
    entries = [{"title": "Apple Inc.", "ticker": "AAPL"}, {"title": "no ticker"}]
    mapping = build_ticker_map(entries)
    assert mapping["APPLE"] == "AAPL"
    assert len(mapping) == 1


def test_parse_holdings_aggregates_multiple_rows_by_cusip():
    root = ET.fromstring(INFO_TABLE_XML)
    holdings = parse_holdings(root)

    assert set(holdings) == {"037833100"}
    holding = holdings["037833100"]
    assert holding["name_of_issuer"] == "APPLE INC"
    assert holding["shares"] == 1004
    assert holding["value_usd"] == 123_956_000  # (123456 + 500) * 1000


def test_diff_to_signal_new_position_is_a_buy():
    signal = diff_to_signal(
        cusip="037833100",
        current={"name_of_issuer": "APPLE INC", "shares": 1000, "value_usd": 100_000},
        prior=None,
        filer_cik="0001234567",
        filer_name="Some Fund LLC",
        period=date(2026, 6, 30),
        total_value=1_000_000,
        ticker_map={"APPLE": "AAPL"},
    )

    assert signal.ticker == "AAPL"
    assert signal.source == "sec_13f"
    assert signal.evidence["change_type"] == "new_position"
    assert signal.evidence["direction"] == "buy"


def test_diff_to_signal_exited_position_is_a_sell():
    signal = diff_to_signal(
        cusip="037833100",
        current=None,
        prior={"name_of_issuer": "APPLE INC", "shares": 1000, "value_usd": 100_000},
        filer_cik="0001234567",
        filer_name="Some Fund LLC",
        period=date(2026, 6, 30),
        total_value=1_000_000,
        ticker_map={"APPLE": "AAPL"},
    )

    assert signal.evidence["change_type"] == "exited"
    assert signal.evidence["direction"] == "sell"


def test_diff_to_signal_skips_unresolved_ticker():
    signal = diff_to_signal(
        cusip="037833100",
        current={"name_of_issuer": "SOME UNKNOWN CO", "shares": 1000, "value_usd": 100_000},
        prior=None,
        filer_cik="0001234567",
        filer_name="Some Fund LLC",
        period=date(2026, 6, 30),
        total_value=1_000_000,
        ticker_map={"APPLE": "AAPL"},
    )

    assert signal is None


def test_diff_to_signal_skips_unchanged_position():
    holding = {"name_of_issuer": "APPLE INC", "shares": 1000, "value_usd": 100_000}
    signal = diff_to_signal(
        cusip="037833100",
        current=holding,
        prior=holding,
        filer_cik="0001234567",
        filer_name="Some Fund LLC",
        period=date(2026, 6, 30),
        total_value=1_000_000,
        ticker_map={"APPLE": "AAPL"},
    )

    assert signal is None
