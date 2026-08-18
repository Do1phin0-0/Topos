import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any


def _text(el: ET.Element, path: str, default: str | None = None) -> str | None:
    node = el.find(path)
    return node.text.strip() if node is not None and node.text else default


def normalize_form4_xml(xml_root: ET.Element, filing_url: str) -> dict[str, Any] | None:
    """Parses one Form 4 ownership document into InsiderTrade fields, or
    None if it's not a usable directional trade (no ticker, or no
    non-derivative transactions to net out a direction from)."""
    ticker = _text(xml_root, "issuer/issuerTradingSymbol")
    if not ticker:
        return None

    is_officer = _text(xml_root, "reportingOwner/reportingOwnerRelationship/isOfficer") == "1"
    is_director = _text(xml_root, "reportingOwner/reportingOwnerRelationship/isDirector") == "1"
    owner_name = _text(xml_root, "reportingOwner/reportingOwnerId/rptOwnerName", default="unknown")

    total_value = 0.0
    net_shares = 0.0
    codes: list[str] = []
    transaction_date: datetime | None = None
    for txn in xml_root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        code = _text(txn, "transactionCoding/transactionCode")
        if not code:
            continue
        shares = float(_text(txn, "transactionAmounts/transactionShares/value", default="0") or 0)
        price = float(_text(txn, "transactionAmounts/transactionPricePerShare/value", default="0") or 0)
        disposed = _text(txn, "transactionAmounts/transactionAcquiredDisposedCode/value")
        codes.append(code)
        net_shares += shares if disposed == "A" else -shares
        total_value += shares * price
        if transaction_date is None:
            raw_date = _text(txn, "transactionDate/value")
            if raw_date:
                try:
                    transaction_date = datetime.strptime(raw_date, "%Y-%m-%d")
                except ValueError:
                    pass

    if not codes or net_shares == 0:
        return None

    return {
        "ticker": ticker.upper(),
        "owner_name": owner_name,
        "is_officer": is_officer,
        "is_director": is_director,
        "transaction_code": codes[0],
        "direction": "buy" if net_shares > 0 else "sell",
        "shares": abs(net_shares),
        "total_value_usd": round(total_value, 2),
        "filing_url": filing_url,
        "transaction_date": transaction_date,
    }
