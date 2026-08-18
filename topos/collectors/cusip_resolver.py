import logging

from topos.db.models import CusipTickerCache
from topos.db.session import SessionLocal
from topos.http import build_session

logger = logging.getLogger(__name__)

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
_BATCH_SIZE = 10


class CusipResolver:
    """Resolves 13F CUSIPs to tradable tickers via OpenFIGI's public
    mapping API (no key required for light use), permanently caching
    results in the DB so a given CUSIP is ever looked up once. Best-effort
    by design: any failure just leaves CUSIPs unresolved (they're skipped
    upstream) rather than raising, since 13F extraction degrading to fewer
    signals should never take down the pipeline the way a hard error
    would."""

    def __init__(self) -> None:
        self._session = build_session(methods=("POST",))

    def resolve(self, cusip: str) -> str | None:
        return self.resolve_many([cusip]).get(cusip)

    def resolve_many(self, cusips: list[str]) -> dict[str, str | None]:
        cusips = sorted({c for c in cusips if c})
        if not cusips:
            return {}

        results: dict[str, str | None] = {}
        db = SessionLocal()
        try:
            cached = {
                row.cusip: row.ticker
                for row in db.query(CusipTickerCache)
                .filter(CusipTickerCache.cusip.in_(cusips))
                .all()
            }
            results.update(cached)
            to_resolve = [c for c in cusips if c not in cached]

            for i in range(0, len(to_resolve), _BATCH_SIZE):
                batch = to_resolve[i : i + _BATCH_SIZE]
                resolved = self._query_openfigi(batch)
                for cusip in batch:
                    ticker = resolved.get(cusip)
                    results[cusip] = ticker
                    db.merge(CusipTickerCache(cusip=cusip, ticker=ticker))
            db.commit()
        finally:
            db.close()

        return results

    def _query_openfigi(self, cusips: list[str]) -> dict[str, str | None]:
        payload = [{"idType": "ID_CUSIP", "idValue": c} for c in cusips]
        try:
            response = self._session.post(OPENFIGI_URL, json=payload, timeout=15)
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, list) or len(body) != len(cusips):
                raise ValueError("unexpected OpenFIGI response shape")
        except Exception:
            logger.warning("CUSIP resolution failed for a batch of %d", len(cusips), exc_info=True)
            return {}

        resolved: dict[str, str | None] = {}
        for cusip, entry in zip(cusips, body):
            data = entry.get("data") or []
            resolved[cusip] = data[0].get("ticker") if data else None
        return resolved
