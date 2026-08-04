from topos.signals.congress import extract_congress_signal


def test_extract_congress_signal_from_house_purchase():
    record = {
        "ticker": "NVDA",
        "type": "purchase",
        "amount": "$100,001 - $250,000",
        "representative": "Jane Rep",
        "chamber": "house",
        "transaction_date": "2026-07-15",
        "disclosure_date": "2026-08-01",
        "ptr_link": "https://example.com/ptr.pdf",
    }

    signal = extract_congress_signal(record)

    assert signal.ticker == "NVDA"
    assert signal.source == "congress_house"
    assert signal.evidence["direction"] == "buy"
    assert signal.evidence["amount_midpoint_usd"] == 175000.5


def test_extract_congress_signal_filters_non_tickers_and_neutral_types():
    assert extract_congress_signal({"ticker": "--", "type": "purchase"}) is None
    assert extract_congress_signal({"ticker": "AAPL", "type": "exchange"}) is None
    assert extract_congress_signal({"ticker": "", "type": "sale_full"}) is None


def test_extract_congress_signal_sale_direction():
    record = {
        "ticker": "TSLA",
        "type": "sale_partial",
        "amount": "$1,001 - $15,000",
        "senator": "John Sen",
        "chamber": "senate",
        "transaction_date": "2026-06-01",
    }

    signal = extract_congress_signal(record)

    assert signal.evidence["direction"] == "sell"
    assert signal.evidence["member"] == "John Sen"
