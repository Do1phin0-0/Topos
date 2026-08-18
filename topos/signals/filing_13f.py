import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from topos.collectors.cusip_resolver import CusipResolver
from topos.collectors.sec_edgar import SECEdgarCollector
from topos.db.models import Filing13FPosition
from topos.db.session import SessionLocal
from topos.signals.base import Signal

# SEC's "current filings" atom feed titles look like:
# "13F-HR - Renaissance Technologies LLC (0001037389) (Filer)"
_TITLE_RE = re.compile(r"^\S+\s*-\s*(?P<name>.+?)\s*\((?P<cik>\d{10})\)")

_MATERIALITY_THRESHOLD = 0.15  # min relative change in position value to count as a signal
_NEW_POSITION_MIN_VALUE = 500_000  # ignore de minimis new stakes as noise


def _strip_namespaces(elem: ET.Element) -> ET.Element:
    """13F informationTable XML declares a default namespace (unlike Form
    4's ownershipDocument), so plain tag lookups like `.find("infoTable")`
    silently return nothing unless namespaces are stripped first."""
    for el in elem.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return elem


def _parse_filer(title: str) -> tuple[str, str] | None:
    match = _TITLE_RE.match(title)
    if not match:
        return None
    return match.group("name").strip(), match.group("cik")


def _parse_holdings(root: ET.Element) -> list[dict[str, Any]]:
    holdings = []
    for entry in root.findall(".//infoTable"):
        cusip = (entry.findtext("cusip") or "").strip()
        if not cusip:
            continue
        try:
            value_usd = float(entry.findtext("value") or 0) * 1000  # reported in thousands
            shares = float(entry.findtext("shrsOrPrnAmt/sshPrnamt") or 0)
        except ValueError:
            continue
        holdings.append(
            {
                "cusip": cusip,
                "name": (entry.findtext("nameOfIssuer") or "").strip(),
                "value_usd": value_usd,
                "shares": shares,
            }
        )
    return holdings


def _extract_holdings_from_filing(collector: SECEdgarCollector, index_url: str) -> list[dict[str, Any]] | None:
    for doc_url in collector.filing_documents(index_url):
        try:
            root = _strip_namespaces(collector.fetch_xml(doc_url))
        except Exception:
            continue
        if root.tag == "informationTable":
            return _parse_holdings(root)
    return None


def _is_newer(candidate: str, stored: str) -> bool:
    try:
        return datetime.fromisoformat(candidate) > datetime.fromisoformat(stored)
    except ValueError:
        return candidate != stored


def _classify(value_usd: float, prior_value: float, is_new: bool) -> tuple[str | None, float | None]:
    if is_new:
        if value_usd < _NEW_POSITION_MIN_VALUE:
            return None, None
        return "new_position", None
    if prior_value <= 0:
        return None, None
    if value_usd == 0:
        return "closed_position", -1.0
    change_pct = (value_usd - prior_value) / prior_value
    if abs(change_pct) < _MATERIALITY_THRESHOLD:
        return None, None
    return ("increased" if change_pct > 0 else "decreased"), change_pct


def _build_signal(
    cik: str,
    filer_name: str,
    filed_at: str,
    holding: dict[str, Any],
    ticker: str,
    direction: str,
    change_pct: float | None,
) -> Signal:
    value_usd = holding["value_usd"]
    size_weight = min(value_usd / 50_000_000, 1.0) * 0.4
    base = 0.35 if direction in ("new_position", "closed_position") else 0.3
    confidence = max(0.0, min(1.0, base + size_weight))

    return Signal(
        timestamp=datetime.now(timezone.utc),
        source="sec_13f",
        ticker=ticker,
        confidence=round(confidence, 3),
        external_id=f"{cik}:{holding['cusip']}:{filed_at}",
        direction="buy" if direction in ("new_position", "increased") else "sell",
        evidence={
            "filer_cik": cik,
            "filer_name": filer_name,
            "cusip": holding["cusip"],
            "name_of_issuer": holding["name"],
            "position_change": direction,
            "change_pct": round(change_pct, 4) if change_pct is not None else None,
            "value_usd": round(value_usd, 2),
            "filed_at": filed_at,
        },
    )


class Filing13FSignalExtractor:
    """Diffs each institutional filer's latest 13F-HR holdings against the
    snapshot stored for that filer+CUSIP (Filing13FPosition), emitting a
    signal when a position is opened, closed, or changes materially.
    CUSIPs are resolved to tradable tickers via a small cached OpenFIGI
    lookup; unresolvable CUSIPs are dropped rather than surfaced with the
    wrong symbol. 13F filings only land quarterly, so most hourly runs
    will find nothing new here — that's expected, not a bug."""

    def __init__(
        self,
        collector: SECEdgarCollector | None = None,
        resolver: CusipResolver | None = None,
    ) -> None:
        self._collector = collector or SECEdgarCollector()
        self._resolver = resolver or CusipResolver()

    def extract(self, limit: int = 10, session: Session | None = None) -> list[Signal]:
        owns_session = session is None
        session = session or SessionLocal()
        signals: list[Signal] = []
        try:
            for filing in self._collector.latest_filings("13F-HR", count=limit):
                parsed_filer = _parse_filer(filing.get("title", ""))
                if not parsed_filer:
                    continue
                filer_name, cik = parsed_filer
                filed_at = filing.get("filed_at", "")
                holdings = _extract_holdings_from_filing(self._collector, filing["index_url"])
                if holdings is None:
                    continue  # no informationTable document found/parseable
                # holdings == [] is a legitimate zero-position filing (e.g.
                # a fund that liquidated everything) and must still run the
                # diff below to detect the resulting full exits.
                signals.extend(self._diff_filing(session, cik, filer_name, filed_at, holdings))
        finally:
            if owns_session:
                session.close()
        return signals

    def _diff_filing(
        self, session: Session, cik: str, filer_name: str, filed_at: str, holdings: list[dict[str, Any]]
    ) -> list[Signal]:
        seen_cusips = {h["cusip"] for h in holdings}
        candidates: list[tuple[dict[str, Any], float, bool]] = []

        for holding in holdings:
            existing = session.query(Filing13FPosition).filter_by(cik=cik, cusip=holding["cusip"]).one_or_none()
            if existing and not _is_newer(filed_at, existing.filed_at):
                continue

            prior_value = existing.value_usd if existing else 0.0
            candidates.append((holding, prior_value, existing is None))

            if existing:
                existing.filed_at = filed_at
                existing.name_of_issuer = holding["name"]
                existing.shares = holding["shares"]
                existing.value_usd = holding["value_usd"]
            else:
                session.add(
                    Filing13FPosition(
                        cik=cik,
                        filer_name=filer_name,
                        cusip=holding["cusip"],
                        name_of_issuer=holding["name"],
                        filed_at=filed_at,
                        shares=holding["shares"],
                        value_usd=holding["value_usd"],
                    )
                )

        # Full exits: positions we had on file for this filer that are
        # simply absent from the new filing (13F only lists current
        # holdings, so a closed position never appears — it just vanishes).
        for row in session.query(Filing13FPosition).filter_by(cik=cik).all():
            if row.cusip in seen_cusips or not _is_newer(filed_at, row.filed_at):
                continue
            candidates.append(
                ({"cusip": row.cusip, "name": row.name_of_issuer, "value_usd": 0.0}, row.value_usd, False)
            )
            session.delete(row)

        session.commit()

        classified = []
        for holding, prior_value, is_new in candidates:
            direction, change_pct = _classify(holding["value_usd"], prior_value, is_new)
            if direction:
                classified.append((holding, direction, change_pct))
        if not classified:
            return []

        tickers = self._resolver.resolve_many([holding["cusip"] for holding, _, _ in classified])

        signals = []
        for holding, direction, change_pct in classified:
            ticker = tickers.get(holding["cusip"])
            if not ticker:
                continue
            signals.append(_build_signal(cik, filer_name, filed_at, holding, ticker, direction, change_pct))
        return signals
