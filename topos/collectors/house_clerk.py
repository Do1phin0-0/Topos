"""Congressional trade disclosures, straight from the House Clerk.

Replaces the House Stock Watcher mirror, which returned AccessDenied at
the bucket level in August 2026 and took the project's only source of
deep, downloadable history with it. This reads the same underlying
filings the mirror was built from:

  1. `{year}FD.zip` holds an XML index of every financial disclosure that
     year, including which are Periodic Transaction Reports (type "P")
     and each one's document id.
  2. `ptr-pdfs/{year}/{doc_id}.pdf` is the report itself.

The tradeoff versus the mirror is honest and worth stating: transaction
detail lives in PDFs. Reports filed electronically carry a real text
layer and parse cleanly; ones filed on paper are scanned images with no
text to extract, and are skipped rather than guessed at. So coverage is
real but partial, and `BackfillResult` reports the parse rate instead of
letting a silent shortfall look like light trading.

Downloads are cached on disk. Re-running a year costs nothing, which
matters because the first run fetches thousands of PDFs and the parser
will need revision once its output has been eyeballed.
"""

import io
import time
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator
from xml.etree import ElementTree

import requests

from topos.collectors.errors import UpstreamUnavailable
from topos.collectors.ptr_parser import parse_report
from topos.config import load_settings

FD_ZIP_URL = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip"
PTR_PDF_URL = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc_id}.pdf"

DEFAULT_CACHE = Path(".cache/house_clerk")


class HouseClerkUnavailable(UpstreamUnavailable):
    """The Clerk's site did not serve a document we expected to exist."""


@dataclass(frozen=True)
class FilingRef:
    """One Periodic Transaction Report listed in a year's index."""

    doc_id: str
    year: int
    member: str
    state_district: str
    filing_date: str | None

    @property
    def pdf_url(self) -> str:
        return PTR_PDF_URL.format(year=self.year, doc_id=self.doc_id)


@dataclass
class BackfillResult:
    """Enough detail to tell a thin harvest from a broken parser.

    The distinction that matters: a filing yielding no transactions is
    usually correct — plenty disclose only bonds, property or index funds
    — but it looks identical, in a count, to one whose table the parser
    could not read. `filings_unreadable` separates them, and `samples`
    keeps the text of a few so the layout can actually be looked at.
    """

    year: int
    filings_indexed: int = 0
    filings_fetched: int = 0
    filings_with_text: int = 0
    filings_with_transactions: int = 0
    filings_unreadable: int = 0
    transactions: list[dict[str, Any]] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)
    drops: Counter = field(default_factory=Counter)
    samples: list[tuple[str, str]] = field(default_factory=list)
    # reason -> a few of the rows discarded for it, so the classification
    # can be checked by eye instead of taken on trust.
    dropped_examples: dict[str, list[str]] = field(default_factory=dict)

    @property
    def parse_rate(self) -> float | None:
        if not self.filings_fetched:
            return None
        return self.filings_with_transactions / self.filings_fetched

    @property
    def unreadable_rate(self) -> float | None:
        """The share that is actually worrying. Unlike `parse_rate`, this
        excludes filings that correctly had nothing to report."""
        if not self.filings_with_text:
            return None
        return self.filings_unreadable / self.filings_with_text

    def summary(self) -> str:
        rate = "—" if self.parse_rate is None else f"{self.parse_rate:.0%}"
        return (
            f"{self.year}: {self.filings_indexed} PTR filings indexed, "
            f"{self.filings_fetched} fetched, {self.filings_with_text} had a text "
            f"layer, {self.filings_with_transactions} yielded transactions "
            f"({rate}), {self.filings_unreadable} unreadable, "
            f"{len(self.transactions)} transactions total, "
            f"{len(self.failures)} failures"
        )

    def diagnosis(self) -> str:
        """Why rows were left out, ordered by how many."""
        if not self.drops:
            return "No rows were dropped."
        width = max(len(reason) for reason in self.drops)
        lines = [
            f"  {reason.ljust(width)}  {count}"
            for reason, count in self.drops.most_common()
        ]
        return "\n".join(["Rows dropped, by reason:", *lines])


def _text_of(pdf_bytes: bytes) -> str:
    """Extracted text, or empty for a scan. Import is local so that the
    parser and index reader stay usable without pdfplumber installed."""
    import pdfplumber

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def parse_index(xml_bytes: bytes) -> list[FilingRef]:
    """The Periodic Transaction Reports in a year's disclosure index.

    Filing types other than "P" are annual reports, candidate filings and
    extension requests — none of which disclose transactions.
    """
    root = ElementTree.fromstring(xml_bytes)
    filings: list[FilingRef] = []

    for member in root.iter("Member"):
        def field_text(name: str) -> str:
            node = member.find(name)
            return (node.text or "").strip() if node is not None else ""

        if not field_text("FilingType").upper().startswith("P"):
            continue

        doc_id = field_text("DocID")
        if not doc_id:
            continue

        name = " ".join(part for part in (field_text("First"), field_text("Last")) if part)
        year = field_text("Year")

        filings.append(
            FilingRef(
                doc_id=doc_id,
                year=int(year) if year.isdigit() else 0,
                member=name or "unknown",
                state_district=field_text("StateDst"),
                filing_date=field_text("FilingDate") or None,
            )
        )

    return filings


class HouseClerkCollector:
    def __init__(
        self,
        *,
        cache_dir: Path | str = DEFAULT_CACHE,
        delay: float = 0.25,
        session: requests.Session | None = None,
    ) -> None:
        self._cache = Path(cache_dir)
        self._delay = delay
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": load_settings().sec_user_agent})

    # --- fetching ----------------------------------------------------

    def _get(self, url: str, cache_path: Path) -> bytes:
        if cache_path.exists():
            return cache_path.read_bytes()

        response = self._session.get(url, timeout=60)
        if response.status_code == 404:
            raise HouseClerkUnavailable(f"Not published: {url}")
        if response.status_code in (401, 403):
            raise HouseClerkUnavailable(
                f"The House Clerk refused the request ({response.status_code}) for\n"
                f"  {url}\n\n"
                "  Public .gov archives do not require credentials, so this is\n"
                "  almost certainly the client being blocked rather than the\n"
                "  document being restricted. Set SEC_EDGAR_USER_AGENT to a real\n"
                "  name and contact address — that value identifies this client to\n"
                "  government sites, and anonymous scrapers get filtered."
            )
        response.raise_for_status()

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(response.content)
        # Only sleep after a real fetch — a cached re-run should be fast.
        time.sleep(self._delay)
        return response.content

    def index(self, year: int) -> list[FilingRef]:
        archive = self._get(
            FD_ZIP_URL.format(year=year), self._cache / f"{year}FD.zip"
        )
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            names = [n for n in bundle.namelist() if n.lower().endswith(".xml")]
            if not names:
                raise HouseClerkUnavailable(
                    f"{year}FD.zip contains no XML index (found: {bundle.namelist()})"
                )
            return parse_index(bundle.read(names[0]))

    def report_pdf(self, filing: FilingRef) -> bytes:
        return self._get(
            filing.pdf_url, self._cache / str(filing.year) / f"{filing.doc_id}.pdf"
        )

    # --- collection --------------------------------------------------

    def transactions(
        self, year: int, *, limit: int | None = None, keep_samples: int = 0
    ) -> BackfillResult:
        result = BackfillResult(year=year)
        filings = self.index(year)
        result.filings_indexed = len(filings)

        for filing in filings[:limit] if limit else filings:
            try:
                pdf = self.report_pdf(filing)
            except (HouseClerkUnavailable, requests.RequestException) as error:
                result.failures.append((filing.doc_id, str(error)))
                continue

            result.filings_fetched += 1

            try:
                text = _text_of(pdf)
            except Exception as error:  # a corrupt PDF is not a reason to stop
                result.failures.append((filing.doc_id, f"unreadable PDF: {error}"))
                continue

            if not text.strip():
                # A scan. Not a failure — there is simply no text in it.
                continue
            result.filings_with_text += 1

            outcome = parse_report(
                text,
                member=filing.member,
                filing_date=filing.filing_date,
                ptr_link=filing.pdf_url,
            )
            result.drops.update(outcome.drops)

            if keep_samples:
                for reason, row in outcome.dropped_rows:
                    kept = result.dropped_examples.setdefault(reason, [])
                    if len(kept) < keep_samples:
                        kept.append(row)

            if outcome.records:
                result.filings_with_transactions += 1
                result.transactions.extend(outcome.records)

            # Checked independently of whether anything parsed: a filing
            # that yields nine transactions and drops a tenth is still
            # losing a disclosure, and is worth looking at.
            if outcome.unreadable:
                result.filings_unreadable += 1
                if len(result.samples) < keep_samples:
                    result.samples.append((filing.doc_id, text))

        return result

    def all_transactions(self, years: Iterator[int] | list[int]) -> list[dict[str, Any]]:
        """Matches the interface the retired collector exposed, so the
        signal extractor and pipeline consume these unchanged."""
        records: list[dict[str, Any]] = []
        for year in years:
            records.extend(self.transactions(year).transactions)
        records.sort(key=lambda r: r.get("transaction_date") or "", reverse=True)
        return records
