"""Turns the text of a House Periodic Transaction Report into records.

Kept as a pure function over already-extracted text, separate from
anything that touches the network or PDF internals, because this is the
part most likely to be wrong: the layout varies between filings, and the
only way to find out is to run it against real reports and inspect what
falls out. A pure function can be tested against a fixture in
milliseconds; a function that downloads a PDF cannot.

Output records match the shape the congressional signal extractor already
consumes, so nothing downstream has to change.

What is deliberately dropped rather than guessed:

* Rows whose transaction date, ticker, or direction cannot be read. A
  half-parsed disclosure with a plausible-looking date is worse than no
  disclosure at all, because a forward return measured from a wrong date
  is indistinguishable from a real result.
* Holdings in funds. A congressman buying an S&P 500 index fund is not a
  view on a company, and treating it as one adds noise wearing the
  costume of signal.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Asset-type codes that denote a pooled vehicle rather than a position in
# one company. A ticker here is the fund's, and the trade says nothing
# about that company in particular.
FUND_ASSET_TYPES = frozenset({"MF", "EF", "ETF", "IF", "CT", "HN", "RP", "PE"})

_TRANSACTION_TYPES = {
    "P": "purchase",
    "S": "sale",
    "E": "exchange",
}

_DATE = re.compile(r"\d{2}/\d{2}/\d{4}")
_TICKER = re.compile(r"\(([A-Z][A-Z0-9.\-]{0,6})\)")
_ASSET_TYPE = re.compile(r"\[([A-Z]{2,3})\]")
# The two halves of a range can end up separated by whatever else wrapped
# into the gap, so the text between them is tolerated (bounded, and
# containing no second amount) and the range is rebuilt from the two
# figures rather than echoed back as matched.
_AMOUNT = re.compile(
    r"(?P<low>\$[\d,]+)\s*-\s*(?:[^$]{0,80}?)(?P<high>\$[\d,]+)"
    r"|Over\s*(?P<floor>\$[\d,]+)",
    re.IGNORECASE,
)

# The transaction-type column, as a token standing alone between spaces.
# `\b[PSE]\b` would be wrong: it matches the S in "U.S. Bancorp".
_TXN_TYPE = re.compile(r"(?:^|\s)([PSE])(?=\s)")


def _iso(us_date: str) -> str | None:
    """MM/DD/YYYY as filed to the ISO form the extractor expects."""
    try:
        return datetime.strptime(us_date, "%m/%d/%Y").date().isoformat()
    except ValueError:
        return None


def _amount(block: str) -> str | None:
    """The disclosed amount range, rebuilt into a canonical form.

    Downstream takes the midpoint of the figures it finds here, so the
    range has to come back as the two numbers actually filed — not with
    whatever wrapped between them along for the ride.
    """
    match = _AMOUNT.search(block)
    if not match:
        return None
    if match.group("floor"):
        return f"Over {match.group('floor')}"
    return f"{match.group('low')} - {match.group('high')}"


def row_blocks(text: str) -> list[str]:
    """Reassemble each table row from the lines the PDF split it across.

    A row's columns all begin on one line, but anything too wide for its
    column wraps onto the lines below — and different columns wrap by
    different amounts, so a long asset name can push its `[ST]` code down
    to sit between the two halves of a wrapped amount range.

    Flattening the whole page instead would interleave those fragments
    with the next row's. Anchoring on the dates works because every
    disclosed transaction has them and nothing else in the table does:
    a line carrying a date starts a row, and the lines after it belong to
    that row until the next one begins.
    """
    blocks: list[list[str]] = []

    for line in text.splitlines():
        if not line.strip():
            continue
        if _DATE.search(line):
            blocks.append([line])
        elif blocks:
            blocks[-1].append(line)

    return [re.sub(r"\s+", " ", " ".join(block)).strip() for block in blocks]


@dataclass
class ParseOutcome:
    """Records, plus why everything else was left out.

    A filing that yields nothing has two very different explanations: it
    disclosed nothing tradeable (bonds, real estate, funds — common and
    correct), or the parser could not read a table that was right there.
    A bare count of transactions cannot tell those apart, and the
    difference is the difference between working and silently losing data.
    """

    records: list[dict[str, Any]] = field(default_factory=list)
    rows_seen: int = 0
    drops: Counter = field(default_factory=Counter)

    @property
    def unreadable(self) -> bool:
        """True when a row named a tradeable asset and still yielded nothing.

        Deliberate exclusions do not count. A row with no ticker is a
        bond, a rental property, a private partnership — the parser saw it
        and correctly passed; likewise an index fund. What counts is a row
        that got past both of those and then could not be finished, which
        means a layout the parser does not handle and a disclosure lost.
        """
        return bool(
            self.drops["no readable date"] + self.drops["no readable direction"]
        )


def parse_report(
    text: str,
    *,
    member: str,
    filing_date: str | None = None,
    ptr_link: str | None = None,
) -> ParseOutcome:
    """Every transaction this report discloses, and an account of the rest.

    `member` and `filing_date` come from the filing index rather than the
    PDF: the index is structured data the Clerk publishes directly, so
    reading identity from there instead of from extracted text removes
    the most error-prone part of the parse.
    """
    outcome = ParseOutcome()

    for block in row_blocks(text):
        outcome.rows_seen += 1

        ticker_match = _TICKER.search(block)
        if not ticker_match:
            # Bonds, real estate, private holdings — no ticker to trade.
            outcome.drops["no ticker"] += 1
            continue

        asset_type_match = _ASSET_TYPE.search(block)
        asset_type = asset_type_match.group(1).upper() if asset_type_match else ""
        if asset_type in FUND_ASSET_TYPES:
            outcome.drops["fund"] += 1
            continue

        # Drop the bracket now that it is captured: a wrapped row can
        # leave it sitting in the middle of the amount range.
        cleaned = _ASSET_TYPE.sub(" ", block)

        dates = _DATE.findall(cleaned)
        transaction_date = _iso(dates[0]) if dates else None
        if transaction_date is None:
            outcome.drops["no readable date"] += 1
            continue

        # The type column sits to the left of the dates. Take the last
        # candidate before the first date — the nearest one to that
        # column, rather than a stray letter earlier in the asset name.
        head = cleaned[: cleaned.index(dates[0])]
        type_matches = _TXN_TYPE.findall(head)
        if not type_matches:
            outcome.drops["no readable direction"] += 1
            continue

        amount = _amount(cleaned)
        if amount is None:
            outcome.drops["no readable amount"] += 1

        outcome.records.append(
            {
                "ticker": ticker_match.group(1).upper(),
                "type": _TRANSACTION_TYPES[type_matches[-1].upper()],
                "amount": amount,
                "transaction_date": transaction_date,
                "disclosure_date": _iso(dates[1]) if len(dates) > 1 else None,
                "representative": member,
                "chamber": "house",
                "ptr_link": ptr_link,
                "asset_type": asset_type or None,
                "partial": "(partial)" in block.lower(),
                "filing_date": filing_date,
            }
        )

    return outcome


def parse_transactions(
    text: str,
    *,
    member: str,
    filing_date: str | None = None,
    ptr_link: str | None = None,
) -> list[dict[str, Any]]:
    """Just the transactions, for callers with no use for the accounting."""
    return parse_report(
        text, member=member, filing_date=filing_date, ptr_link=ptr_link
    ).records
