import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone

from topos.collectors.openfigi import OpenFigiCollector
from topos.collectors.sec_edgar import SECEdgarCollector
from topos.signals.base import Signal

_INCREASE_THRESHOLD = 0.10  # 10%+ share increase, or a brand-new position
_MAX_FILERS_PER_RUN = 5  # each filer costs a filing_history call + 2 holdings tables


def _parse_filed_date(raw: str | None) -> date | None:
    """The atom feed's `updated` field, e.g. '2026-08-05T14:31:02-04:00'."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _strip_namespaces(elem: ET.Element) -> ET.Element:
    for el in elem.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return elem


def _parse_holdings(root: ET.Element) -> dict[str, dict]:
    holdings: dict[str, dict] = {}
    for info in root.findall(".//infoTable"):
        cusip = (info.findtext("cusip") or "").strip()
        if not cusip:
            continue
        shares = float(info.findtext("shrsOrPrnAmt/sshPrnAmt", default="0") or 0)
        issuer = (info.findtext("nameOfIssuer") or "").strip()
        holdings[cusip] = {"shares": shares, "issuer": issuer}
    return holdings


class InstitutionalSignalExtractor:
    """Detects institutional ownership increases by diffing a fund's
    latest 13F-HR against its own prior-quarter 13F-HR. Institutional
    filers are processed one at a time (capped at 5/run — this is
    genuinely expensive: a filing-history lookup plus two holdings tables
    per filer), and holdings are matched prior-vs-current entirely by
    CUSIP, since that's what 13F filings actually report."""

    def __init__(
        self,
        collector: SECEdgarCollector | None = None,
        figi: OpenFigiCollector | None = None,
    ) -> None:
        self._collector = collector or SECEdgarCollector()
        self._figi = figi or OpenFigiCollector()

    def extract(self, limit: int = 40) -> list[Signal]:
        signals: list[Signal] = []
        filer_count = min(limit, _MAX_FILERS_PER_RUN)
        for filing in self._collector.latest_filings("13F-HR", count=filer_count):
            cik = filing.get("cik")
            if cik is None:
                continue
            try:
                signals.extend(self._extract_for_filer(cik, filing))
            except Exception:
                continue
        return signals

    def _extract_for_filer(self, cik: int, current_filing: dict) -> list[Signal]:
        current_holdings = self._holdings_for_filing(current_filing["index_url"])
        if not current_holdings:
            return []

        prior_filing = self._find_prior_13f(cik, current_filing["index_url"])
        if prior_filing is None:
            return []
        prior_holdings = self._holdings_for_filing(prior_filing["index_url"])

        increases = self._diff(prior_holdings, current_holdings)
        if not increases:
            return []

        # 13F holdings are disclosed with a lag, but the filing date is
        # when the market could first act on them — that's the event.
        event_date = _parse_filed_date(current_filing.get("filed_at"))
        if event_date is None:
            return []

        tickers = self._figi.cusips_to_tickers(list(increases.keys()))
        signals = []
        for cusip, change in increases.items():
            ticker = tickers.get(cusip)
            if not ticker:
                continue
            signals.append(
                Signal(
                    timestamp=datetime.now(timezone.utc),
                    event_date=event_date,
                    # One filer's disclosed change in one holding.
                    dedup_key=f"institutional_13f:{current_filing['index_url']}:{cusip}",
                    source="institutional_13f",
                    ticker=ticker,
                    confidence=change["confidence"],
                    evidence={
                        "direction": "buy",
                        "cik": cik,
                        "issuer": change["issuer"],
                        "shares_prior": change["shares_prior"],
                        "shares_current": change["shares_current"],
                        "pct_change": change["pct_change"],
                        "filing_url": current_filing["index_url"],
                    },
                )
            )
        return signals

    def _find_prior_13f(self, cik: int, current_index_url: str) -> dict | None:
        history = self._collector.filing_history(cik, count=80)
        thirteen_fs = [f for f in history if f["form_type"] == "13F-HR"]
        thirteen_fs.sort(key=lambda f: f["filing_date"], reverse=True)
        for i, f in enumerate(thirteen_fs):
            if f["index_url"] == current_index_url and i + 1 < len(thirteen_fs):
                return thirteen_fs[i + 1]
        return thirteen_fs[1] if len(thirteen_fs) > 1 else None

    def _holdings_for_filing(self, index_url: str) -> dict[str, dict]:
        for doc in self._collector.filing_documents(index_url):
            if not doc["name"].lower().endswith(".xml"):
                continue
            try:
                root = _strip_namespaces(self._collector.fetch_xml(doc["url"]))
            except Exception:
                continue
            if root.tag != "informationTable":
                continue
            return _parse_holdings(root)
        return {}

    def _diff(self, prior: dict[str, dict], current: dict[str, dict]) -> dict[str, dict]:
        increases: dict[str, dict] = {}
        for cusip, curr in current.items():
            prior_shares = prior.get(cusip, {}).get("shares", 0.0)
            pct_change = 1.0 if prior_shares == 0 else (curr["shares"] - prior_shares) / prior_shares
            if pct_change < _INCREASE_THRESHOLD:
                continue
            confidence = max(0.0, min(1.0, 0.3 + min(pct_change, 1.0) * 0.5))
            increases[cusip] = {
                "issuer": curr["issuer"],
                "shares_prior": prior_shares,
                "shares_current": curr["shares"],
                "pct_change": round(pct_change, 3),
                "confidence": round(confidence, 3),
            }
        return increases
