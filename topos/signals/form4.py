import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone

from topos.collectors.sec_edgar import SECEdgarCollector
from topos.signals.base import Signal


def _text(el: ET.Element, path: str, default: str | None = None) -> str | None:
    node = el.find(path)
    return node.text.strip() if node is not None and node.text else default


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def extract_form4_signal(xml_root: ET.Element, filing_url: str) -> Signal | None:
    ticker = _text(xml_root, "issuer/issuerTradingSymbol")
    if not ticker:
        return None

    is_officer = _text(xml_root, "reportingOwner/reportingOwnerRelationship/isOfficer") == "1"
    is_director = _text(xml_root, "reportingOwner/reportingOwnerRelationship/isDirector") == "1"
    owner_name = _text(xml_root, "reportingOwner/reportingOwnerId/rptOwnerName", default="unknown")

    total_value = 0.0
    net_shares = 0.0
    codes: list[str] = []
    transaction_dates: list[date] = []
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
        txn_date = _parse_date(_text(txn, "transactionDate/value"))
        if txn_date:
            transaction_dates.append(txn_date)

    if not codes:
        return None

    # The insider's actual trade date, not when we scraped the filing.
    # periodOfReport is the fallback; a filing we can't date at all is
    # dropped rather than backdated to today, which would corrupt any
    # forward-return measured from it.
    event_date = min(transaction_dates) if transaction_dates else _parse_date(
        _text(xml_root, "periodOfReport")
    )
    if event_date is None:
        return None

    direction = "buy" if net_shares > 0 else "sell" if net_shares < 0 else "neutral"
    role_weight = 0.3 if (is_officer or is_director) else 0.15
    size_weight = min(total_value / 1_000_000, 1.0) * 0.5
    confidence = max(0.0, min(1.0, 0.2 + role_weight + size_weight))

    return Signal(
        timestamp=datetime.now(timezone.utc),
        event_date=event_date,
        # One Form 4 filing yields at most one signal, so the filing URL
        # is the natural identity.
        dedup_key=f"sec_form4:{filing_url}",
        source="sec_form4",
        ticker=ticker.upper(),
        confidence=round(confidence, 3),
        evidence={
            "filing_url": filing_url,
            "owner": owner_name,
            "is_officer": is_officer,
            "is_director": is_director,
            "transaction_codes": codes,
            "net_shares": net_shares,
            "total_value_usd": round(total_value, 2),
            "direction": direction,
        },
    )


class Form4SignalExtractor:
    def __init__(self, collector: SECEdgarCollector | None = None) -> None:
        self._collector = collector or SECEdgarCollector()

    def extract(self, limit: int = 20) -> list[Signal]:
        signals: list[Signal] = []
        for filing in self._collector.latest_filings("4", count=limit):
            for doc in self._collector.filing_documents(filing["index_url"]):
                if not doc["name"].endswith(".xml"):
                    continue
                try:
                    root = self._collector.fetch_xml(doc["url"])
                except Exception:
                    continue
                if not root.tag.endswith("ownershipDocument"):
                    continue
                signal = extract_form4_signal(root, filing["index_url"])
                if signal:
                    signals.append(signal)
                break
        return signals
