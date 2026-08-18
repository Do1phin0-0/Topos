import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from typing import Any, Callable

from sqlalchemy import func
from sqlalchemy.orm import Session

from topos.collectors.sec_edgar import SECEdgarCollector
from topos.db.models import Filing13FHolding
from topos.db.session import SessionLocal
from topos.signals.base import Signal

# Words dropped when normalizing issuer/company names for fuzzy matching —
# 13F filings and SEC's ticker list format the same company's name
# differently (e.g. "APPLE INC" vs "Apple Inc."), so exact string equality
# rarely works.
_SUFFIX_WORDS = {
    "INC", "CORP", "CORPORATION", "CO", "COMPANY", "LLC", "LTD", "LP", "PLC",
    "THE", "COM", "NEW", "HOLDINGS", "HOLDING", "CLASS", "A", "B", "C",
}


def _local_tag(el: ET.Element) -> str:
    return el.tag.rsplit("}", 1)[-1]


def _normalize_title(title: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9 ]", " ", title.upper())
    words = [w for w in cleaned.split() if w not in _SUFFIX_WORDS]
    return " ".join(words)


def build_ticker_map(entries: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for entry in entries:
        title, ticker = entry.get("title"), entry.get("ticker")
        if not title or not ticker:
            continue
        key = _normalize_title(title)
        if key and key not in mapping:
            mapping[key] = ticker
    return mapping


def parse_holdings(info_root: ET.Element) -> dict[str, dict[str, Any]]:
    """Aggregates infoTable entries by CUSIP (a filer can report the same
    issuer more than once, e.g. across share classes)."""
    holdings: dict[str, dict[str, Any]] = {}
    for info in info_root.findall(".//{*}infoTable"):
        cusip = info.findtext("{*}cusip")
        if not cusip:
            continue
        cusip = cusip.strip()
        name_of_issuer = (info.findtext("{*}nameOfIssuer") or "").strip()
        value_thousands = float(info.findtext("{*}value", default="0") or 0)
        shares = float(info.findtext("{*}shrsOrPrnAmt/{*}sshPrnamt", default="0") or 0)

        agg = holdings.setdefault(cusip, {"name_of_issuer": name_of_issuer, "shares": 0.0, "value_usd": 0.0})
        if name_of_issuer:
            agg["name_of_issuer"] = name_of_issuer
        agg["shares"] += shares
        agg["value_usd"] += value_thousands * 1000  # infoTable value is reported in thousands of USD
    return holdings


def diff_to_signal(
    *,
    cusip: str,
    current: dict[str, Any] | None,
    prior: dict[str, Any] | None,
    filer_cik: str,
    filer_name: str | None,
    period: date,
    total_value: float,
    ticker_map: dict[str, str],
) -> Signal | None:
    current_shares = current["shares"] if current else 0.0
    prior_shares = prior["shares"] if prior else 0.0
    delta_shares = current_shares - prior_shares
    if delta_shares == 0:
        return None

    if prior is None:
        change_type, direction, type_weight = "new_position", "buy", 0.35
    elif current is None:
        change_type, direction, type_weight = "exited", "sell", 0.3
    elif delta_shares > 0:
        change_type, direction, type_weight = "increased", "buy", 0.2
    else:
        change_type, direction, type_weight = "decreased", "sell", 0.15

    name_of_issuer = (current or prior)["name_of_issuer"]
    ticker = ticker_map.get(_normalize_title(name_of_issuer or ""))
    if not ticker:
        return None

    current_value = current["value_usd"] if current else 0.0
    prior_value = prior["value_usd"] if prior else 0.0
    size_weight = min(abs(current_value - prior_value) / (total_value or 1.0), 1.0) * 0.4
    confidence = max(0.0, min(1.0, 0.15 + type_weight + size_weight))

    return Signal(
        timestamp=datetime.now(timezone.utc),
        source="sec_13f",
        ticker=ticker,
        confidence=round(confidence, 3),
        evidence={
            "filer_cik": filer_cik,
            "filer_name": filer_name,
            "cusip": cusip,
            "name_of_issuer": name_of_issuer,
            "period_of_report": period.isoformat(),
            "change_type": change_type,
            "direction": direction,
            "prior_shares": prior_shares,
            "current_shares": current_shares,
            "delta_shares": delta_shares,
            "prior_value_usd": round(prior_value, 2),
            "current_value_usd": round(current_value, 2),
        },
    )


class Filing13FSignalExtractor:
    """Diffs each filer's 13F-HR holdings against their previous quarter's
    filing (stored in `filing_13f_holdings`) to turn static snapshots into
    buy/sell signals. A filer's first-ever filing has nothing to diff
    against, so it's stored as a baseline with no signal emitted.

    Caveat: 13F filings identify issuers by CUSIP + name, never a ticker.
    CUSIP-to-ticker mapping is a licensed CUSIP Global Services product, so
    there's no free official lookup. Resolution here is a best-effort fuzzy
    match against SEC's own company_tickers.json by normalized name;
    holdings that don't match a known ticker are skipped rather than
    guessed at."""

    def __init__(
        self,
        collector: SECEdgarCollector | None = None,
        session_factory: Callable[[], Session] = SessionLocal,
    ) -> None:
        self._collector = collector or SECEdgarCollector()
        self._session_factory = session_factory

    def extract(self, limit: int = 20) -> list[Signal]:
        signals: list[Signal] = []
        session = self._session_factory()
        try:
            ticker_map = build_ticker_map(self._collector.company_tickers())

            for filing in self._collector.latest_filings("13F-HR", count=limit):
                primary_root: ET.Element | None = None
                info_root: ET.Element | None = None
                for doc_url in self._collector.filing_documents(filing["index_url"]):
                    try:
                        root = self._collector.fetch_xml(doc_url)
                    except Exception:
                        continue
                    tag = _local_tag(root)
                    if tag == "edgarSubmission":
                        primary_root = root
                    elif tag == "informationTable":
                        info_root = root
                    if primary_root is not None and info_root is not None:
                        break
                if primary_root is None or info_root is None:
                    continue

                filer_cik = primary_root.findtext(".//{*}cik")
                filer_name = primary_root.findtext(".//{*}filingManager/{*}name")
                period_text = primary_root.findtext(".//{*}periodOfReport")
                if not filer_cik or not period_text:
                    continue
                try:
                    period = datetime.strptime(period_text.strip(), "%m-%d-%Y").date()
                except ValueError:
                    continue

                already_ingested = (
                    session.query(Filing13FHolding.id)
                    .filter_by(filer_cik=filer_cik, period_of_report=period)
                    .first()
                    is not None
                )
                if already_ingested:
                    continue

                current_holdings = parse_holdings(info_root)
                if not current_holdings:
                    continue

                latest_prior_period = (
                    session.query(func.max(Filing13FHolding.period_of_report))
                    .filter(
                        Filing13FHolding.filer_cik == filer_cik,
                        Filing13FHolding.period_of_report < period,
                    )
                    .scalar()
                )

                if latest_prior_period is not None:
                    prior_rows = (
                        session.query(Filing13FHolding)
                        .filter_by(filer_cik=filer_cik, period_of_report=latest_prior_period)
                        .all()
                    )
                    prior_holdings = {
                        row.cusip: {"name_of_issuer": row.name_of_issuer, "shares": row.shares, "value_usd": row.value_usd}
                        for row in prior_rows
                    }
                    total_value = sum(h["value_usd"] for h in current_holdings.values())
                    for cusip in set(current_holdings) | set(prior_holdings):
                        signal = diff_to_signal(
                            cusip=cusip,
                            current=current_holdings.get(cusip),
                            prior=prior_holdings.get(cusip),
                            filer_cik=filer_cik,
                            filer_name=filer_name,
                            period=period,
                            total_value=total_value,
                            ticker_map=ticker_map,
                        )
                        if signal:
                            signals.append(signal)

                for cusip, holding in current_holdings.items():
                    session.add(
                        Filing13FHolding(
                            filer_cik=filer_cik,
                            filer_name=filer_name or "unknown",
                            period_of_report=period,
                            cusip=cusip,
                            name_of_issuer=holding["name_of_issuer"],
                            shares=holding["shares"],
                            value_usd=holding["value_usd"],
                        )
                    )
            session.commit()
        finally:
            session.close()
        return signals
