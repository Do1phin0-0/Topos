from titan.app.signals.congress import normalize_congress_record


def test_normalize_house_purchase():
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

    normalized = normalize_congress_record(record)

    assert normalized["ticker"] == "NVDA"
    assert normalized["transaction_type"] == "purchase"
    assert normalized["amount_midpoint_usd"] == 175000.5
    assert normalized["member"] == "Jane Rep"


def test_normalize_senate_sale():
    record = {
        "ticker": "TSLA",
        "type": "sale_partial",
        "amount": "$1,001 - $15,000",
        "senator": "John Sen",
        "chamber": "senate",
        "transaction_date": "2026-06-01",
    }

    normalized = normalize_congress_record(record)

    assert normalized["transaction_type"] == "sale"
    assert normalized["member"] == "John Sen"


def test_normalize_filters_non_tickers_exchanges_and_missing_dates():
    assert normalize_congress_record({"ticker": "--", "type": "purchase", "transaction_date": "2026-01-01"}) is None
    assert normalize_congress_record({"ticker": "AAPL", "type": "exchange", "transaction_date": "2026-01-01"}) is None
    assert normalize_congress_record({"ticker": "AAPL", "type": "purchase", "transaction_date": None}) is None
    assert normalize_congress_record({"ticker": "AAPL", "type": "purchase", "transaction_date": "not-a-date"}) is None
