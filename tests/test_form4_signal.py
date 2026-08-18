import xml.etree.ElementTree as ET

from topos.signals.form4 import extract_form4_signal

_FILING_URL = "https://www.sec.gov/Archives/edgar/data/0000000000/0000000000-24-000001-index.htm"


def _build_xml(
    *,
    ticker: str = "ACME",
    is_officer: str = "1",
    is_director: str = "0",
    owner: str = "Jane Doe",
    shares: str = "1000",
    price: str = "50",
    disposed_code: str = "A",
    transaction_code: str = "P",
) -> ET.Element:
    root = ET.Element("ownershipDocument")

    issuer = ET.SubElement(root, "issuer")
    ET.SubElement(issuer, "issuerTradingSymbol").text = ticker

    owner_el = ET.SubElement(root, "reportingOwner")
    rel = ET.SubElement(owner_el, "reportingOwnerRelationship")
    ET.SubElement(rel, "isOfficer").text = is_officer
    ET.SubElement(rel, "isDirector").text = is_director
    owner_id = ET.SubElement(owner_el, "reportingOwnerId")
    ET.SubElement(owner_id, "rptOwnerName").text = owner

    table = ET.SubElement(root, "nonDerivativeTable")
    txn = ET.SubElement(table, "nonDerivativeTransaction")
    coding = ET.SubElement(txn, "transactionCoding")
    ET.SubElement(coding, "transactionCode").text = transaction_code
    amounts = ET.SubElement(txn, "transactionAmounts")
    shares_el = ET.SubElement(amounts, "transactionShares")
    ET.SubElement(shares_el, "value").text = shares
    price_el = ET.SubElement(amounts, "transactionPricePerShare")
    ET.SubElement(price_el, "value").text = price
    disposed_el = ET.SubElement(amounts, "transactionAcquiredDisposedCode")
    ET.SubElement(disposed_el, "value").text = disposed_code

    return root


def test_extract_form4_signal_officer_buy():
    root = _build_xml(ticker="acme", is_officer="1", shares="1000", price="50", disposed_code="A")

    signal = extract_form4_signal(root, _FILING_URL)

    assert signal is not None
    assert signal.ticker == "ACME"
    assert signal.source == "sec_form4"
    assert signal.external_id == _FILING_URL
    assert signal.evidence["direction"] == "buy"
    assert signal.evidence["is_officer"] is True
    assert signal.evidence["total_value_usd"] == 50_000.0
    # officer + $50k -> above the base 0.2 floor
    assert signal.confidence > 0.2


def test_extract_form4_signal_sale_direction():
    root = _build_xml(disposed_code="D", transaction_code="S")

    signal = extract_form4_signal(root, _FILING_URL)

    assert signal.evidence["direction"] == "sell"
    assert signal.evidence["net_shares"] == -1000.0


def test_extract_form4_signal_returns_none_without_ticker():
    root = ET.Element("ownershipDocument")
    ET.SubElement(root, "issuer")

    assert extract_form4_signal(root, _FILING_URL) is None


def test_extract_form4_signal_returns_none_without_transactions():
    root = ET.Element("ownershipDocument")
    issuer = ET.SubElement(root, "issuer")
    ET.SubElement(issuer, "issuerTradingSymbol").text = "ACME"
    ET.SubElement(root, "nonDerivativeTable")

    assert extract_form4_signal(root, _FILING_URL) is None
