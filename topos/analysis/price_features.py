"""Price-action features, computed point-in-time from stored daily bars.

Every function here takes the *full* bar history plus an index `i` and
answers "what would this feature have read as of bar i" — never a
truncated list the caller is responsible for slicing correctly. That is
deliberate: `event_date` bugs are the recurring failure mode across this
whole project (see docs/DATA_LINEAGE.md), and a function signature that
requires the point-in-time cutoff as an explicit argument cannot be
called with silent look-ahead the way `feature(bars_so_far)` can if a
caller ever passes one bar too many.

Pure and DB-free by design, same split as `ptr_parser.py` versus
`house_clerk.py`: these are the part most likely to have a subtle
off-by-one, so they need to be testable against a handful of numbers in
milliseconds, not against a database.
"""

from topos.collectors.prices import Bar


def gap_pct(bars: list[Bar], i: int) -> float | None:
    """Bar i's open versus bar i-1's close — the overnight move a trader
    would have seen at bar i's open, before that bar's own session even
    started. None on the first bar of a ticker's history, where there is
    no prior close to gap from, and on a non-positive prior close (bad or
    delisted data, never a divide-by-zero)."""
    if i < 1 or i >= len(bars):
        return None
    prev_close = bars[i - 1].close
    if prev_close <= 0:
        return None
    return (bars[i].open - prev_close) / prev_close


def relative_volume(bars: list[Bar], i: int, window: int = 20) -> float | None:
    """Bar i's volume against the average of the `window` bars *before*
    it — bar i itself is excluded from its own baseline. Including it
    would let a huge spike day inflate the very average it is being
    compared to, mechanically pulling its own reading back down toward
    1.0 and understating exactly the days this is meant to flag."""
    if i < window or i >= len(bars):
        return None
    trailing = bars[i - window : i]
    avg = sum(b.volume for b in trailing) / window
    if avg <= 0:
        return None
    return bars[i].volume / avg


def trailing_return(bars: list[Bar], i: int, window: int) -> float | None:
    """Return from bar i-window's close to bar i's close: the trend as of
    bar i, using only bars up to and including it. None when there isn't
    `window` bars of history yet, or the starting close is non-positive."""
    if i < window or i >= len(bars):
        return None
    start = bars[i - window].close
    if start <= 0:
        return None
    return (bars[i].close - start) / start
