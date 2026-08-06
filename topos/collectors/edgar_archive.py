"""Historical SEC filings via EDGAR's quarterly full-index archive.

The live collector reads EDGAR's "most recent filings" atom feed, which
is right for a running pipeline and useless for validation: it shows what
was filed in the last few hours. Backtesting needs years.

EDGAR publishes a `master.idx` per quarter back to 1993 — every filing,
with CIK, form type, filing date and path. That plus the filing itself is
a complete historical record, no API key.

**The volume problem, and why this filters by CIK.** Roughly a quarter of
a million Form 4s are filed per year. Downloading them all would take
about a day at SEC's rate limit and is pointless here: a Form 4 for a
company Topos has no other signal or price history on cannot contribute
to a multi-source comparison. So the caller supplies the CIKs worth
fetching, derived from tickers already in the database, and the index is
filtered before anything is downloaded.

Extracted XML is cached, not the full submission text — the submission
carries a rendered HTML copy that can be ten times the size of the part
we want, and disk on a laptop is finite.
"""

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import requests

from topos.collectors.errors import UpstreamUnavailable
from topos.config import load_settings

FULL_INDEX_URL = "https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{quarter}/master.idx"
ARCHIVE_URL = "https://www.sec.gov/Archives/{path}"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

DEFAULT_CACHE = Path(".cache/edgar")

# SEC asks for no more than 10 requests/second and will block clients that
# ignore it. 0.12s leaves headroom.
DEFAULT_DELAY = 0.12

_OWNERSHIP = re.compile(
    rb"<ownershipDocument>.*?</ownershipDocument>", re.DOTALL | re.IGNORECASE
)


class EdgarUnavailable(UpstreamUnavailable):
    """EDGAR did not serve something we expected to exist."""


@dataclass(frozen=True)
class IndexEntry:
    """One filing listed in a quarterly index."""

    cik: int
    company: str
    form_type: str
    filed: date
    path: str  # e.g. edgar/data/320193/0000320193-24-000006.txt

    @property
    def accession(self) -> str:
        return self.path.rsplit("/", 1)[-1].removesuffix(".txt")

    @property
    def url(self) -> str:
        return ARCHIVE_URL.format(path=self.path)


@dataclass
class ArchiveResult:
    """What a quarter's harvest produced, and what it lost on the way."""

    year: int
    quarter: int
    filings_in_index: int = 0
    filings_matched: int = 0
    filings_fetched: int = 0
    filings_parsed: int = 0
    signals: list = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)

    @property
    def parse_rate(self) -> float | None:
        if not self.filings_fetched:
            return None
        return self.filings_parsed / self.filings_fetched

    def summary(self) -> str:
        rate = "—" if self.parse_rate is None else f"{self.parse_rate:.0%}"
        return (
            f"{self.year}Q{self.quarter}: {self.filings_in_index} filings indexed, "
            f"{self.filings_matched} matched our tickers, {self.filings_fetched} fetched, "
            f"{self.filings_parsed} parsed ({rate}), {len(self.signals)} signals, "
            f"{len(self.failures)} failures"
        )


def parse_master_index(text: str, form_type: str | None = None) -> list[IndexEntry]:
    """Parses a quarterly `master.idx`.

    Format is `CIK|Company|Form Type|Date Filed|Filename` after a header
    block. Malformed lines are skipped rather than raising — one bad row
    in a 300,000-line index must not cost the whole quarter.
    """
    entries: list[IndexEntry] = []

    for line in text.splitlines():
        parts = line.split("|")
        if len(parts) != 5:
            continue
        raw_cik, company, form, filed, path = (p.strip() for p in parts)
        if not raw_cik.isdigit():
            continue  # header rows and the ---- separator
        if form_type is not None and form != form_type:
            continue
        try:
            filed_date = datetime.strptime(filed, "%Y-%m-%d").date()
        except ValueError:
            continue
        entries.append(
            IndexEntry(
                cik=int(raw_cik),
                company=company,
                form_type=form,
                filed=filed_date,
                path=path,
            )
        )

    return entries


def extract_ownership_xml(submission: bytes) -> ET.Element | None:
    """Pulls the ownershipDocument out of a full submission file.

    A Form 4 submission wraps its XML in SGML headers and often bundles a
    rendered HTML version alongside. Slicing out the element by name is
    more robust than assuming a document order that varies by filer agent.
    """
    match = _OWNERSHIP.search(submission)
    if not match:
        return None
    try:
        return ET.fromstring(match.group(0))
    except ET.ParseError:
        return None


class EdgarArchiveCollector:
    def __init__(
        self,
        *,
        cache_dir: Path | str = DEFAULT_CACHE,
        delay: float = DEFAULT_DELAY,
        session: requests.Session | None = None,
    ) -> None:
        self._cache = Path(cache_dir)
        self._delay = delay
        self._session = session or requests.Session()
        # SEC requires a descriptive User-Agent naming a real contact.
        self._session.headers.update({"User-Agent": load_settings().sec_user_agent})
        self._ticker_to_cik: dict[str, int] | None = None

    # --- fetching ----------------------------------------------------

    def _get(self, url: str, cache_path: Path | None = None) -> bytes:
        if cache_path is not None and cache_path.exists():
            return cache_path.read_bytes()

        response = self._session.get(url, timeout=30)
        if response.status_code == 404:
            raise EdgarUnavailable(f"Not published: {url}")
        if response.status_code in (401, 403):
            raise EdgarUnavailable(
                f"EDGAR refused the request ({response.status_code}) for\n  {url}\n\n"
                "  SEC requires a User-Agent naming a real person and contact\n"
                "  address, and blocks clients that do not send one. Set\n"
                "  SEC_EDGAR_USER_AGENT in your .env to something like\n"
                "  'Aaron Aleman aaron@example.com'."
            )
        response.raise_for_status()

        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(response.content)
        time.sleep(self._delay)  # only after a real fetch
        return response.content

    def ticker_to_cik(self) -> dict[str, int]:
        """SEC's own ticker↔CIK mapping, so an index can be filtered to
        the companies we actually hold other data for."""
        if self._ticker_to_cik is None:
            raw = self._get(COMPANY_TICKERS_URL, self._cache / "company_tickers.json")
            import json

            try:
                data = json.loads(raw)
            except ValueError as error:
                raise EdgarUnavailable(f"Could not read the ticker map: {error}") from error
            self._ticker_to_cik = {
                row["ticker"].upper(): int(row["cik_str"]) for row in data.values()
            }
        return self._ticker_to_cik

    def ciks_for(self, tickers: Iterable[str]) -> set[int]:
        mapping = self.ticker_to_cik()
        return {mapping[t.upper()] for t in tickers if t.upper() in mapping}

    def index(self, year: int, quarter: int, form_type: str = "4") -> list[IndexEntry]:
        raw = self._get(
            FULL_INDEX_URL.format(year=year, quarter=quarter),
            self._cache / f"master-{year}Q{quarter}.idx",
        )
        # EDGAR indexes are latin-1; a stray byte must not kill the quarter.
        return parse_master_index(raw.decode("latin-1", errors="replace"), form_type=form_type)

    def filing_xml(self, entry: IndexEntry) -> ET.Element | None:
        cache_path = self._cache / f"{entry.filed.year}Q{(entry.filed.month - 1) // 3 + 1}" / f"{entry.accession}.xml"
        if cache_path.exists():
            try:
                return ET.fromstring(cache_path.read_bytes())
            except ET.ParseError:
                cache_path.unlink()  # a truncated cache entry; refetch

        submission = self._get(entry.url)
        root = extract_ownership_xml(submission)
        if root is None:
            return None

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(ET.tostring(root))
        return root

    # --- collection --------------------------------------------------

    def form4_signals(
        self,
        year: int,
        quarter: int,
        *,
        ciks: set[int] | None = None,
        limit: int | None = None,
    ) -> ArchiveResult:
        """Form 4 signals for one quarter, restricted to `ciks` if given.

        Import is local because this module is about fetching; the signal
        shape belongs to the extractor, and keeping the dependency one-way
        means the parser can be tested without any of this.
        """
        from topos.signals.form4 import extract_form4_signal

        result = ArchiveResult(year=year, quarter=quarter)
        entries = self.index(year, quarter, form_type="4")
        result.filings_in_index = len(entries)

        if ciks is not None:
            entries = [e for e in entries if e.cik in ciks]
        result.filings_matched = len(entries)

        for entry in entries[:limit] if limit else entries:
            try:
                root = self.filing_xml(entry)
            except (EdgarUnavailable, requests.RequestException) as error:
                result.failures.append((entry.accession, str(error)))
                continue

            result.filings_fetched += 1
            if root is None:
                # No ownershipDocument: a paper filing or an amendment
                # style this does not read. Not a crash, just nothing.
                continue
            result.filings_parsed += 1

            signal = extract_form4_signal(root, entry.url)
            if signal:
                result.signals.append(signal)

        return result
