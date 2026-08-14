"""Price-action signals: gap, relative volume, momentum, and reversal.

Congressional disclosures and Form 4 filings both came back null in
validation, and both share a trait that could explain it: they are public
information arriving weeks after the fact, competing against a market
that has already priced them in. This tests a genuinely different
hypothesis — that the market's own recent behaviour predicts what it does
next — using nothing but the daily bars already sitting in `price_bars`.
No network call, no new data source, no subscription.

Two of the four are deliberately the most heavily studied effects in
equity markets (momentum, short-term reversal) rather than something
novel. That is a feature, not a limitation: if a well-documented effect
does not show up here, the honest conclusion is a bug in this pipeline,
not that momentum stopped existing. A null result on an invented feature
proves nothing; a null result on momentum is informative either way.

**Rolling conditions versus discrete events.** A congressional trade or a
Form 4 filing happens once. Momentum and reversal are properties of a
*window* that stays true for as long as the underlying trend persists —
sampled every day, the same six-week rally would fire the same signal on
dozens of consecutive days, each with a 20-day forward-return window that
overlaps almost entirely with its neighbours. That inflates the sample
size without adding independent evidence, which is exactly the reasoning
`replay_rankings.py` already applies to snapshot spacing (see its
`DEFAULT_STEP_DAYS` comment). The same discipline is applied here via
`MIN_SIGNAL_SPACING_DAYS`: once a source fires for a ticker, it goes
quiet for that many trading days before it can fire again for that same
ticker, regardless of how long the underlying condition persists.

**Direction conventions**, stated up front because two of the four bet
opposite ways on the same kind of move:

* Gap, relative volume, and momentum bet on *continuation* — a gap up,
  an unusual-volume up day, and a rising trend are all read as bullish.
* Reversal bets *against* the recent move — a sharp 5-day drop is read
  as bullish (a bounce), a sharp rise as bearish (a pullback). This is
  the standard short-term mean-reversion hypothesis, deliberately the
  opposite convention from momentum.

Whichever convention is wrong for a given source will show up as a
negative correlation in validation, same as it would for any other
source — the point-in-time and dedup discipline is what makes that
number trustworthy, not which direction was guessed.
"""

from datetime import datetime, timezone
from typing import Callable

from topos.analysis.price_features import gap_pct, relative_volume, trailing_return
from topos.collectors.prices import Bar
from topos.signals.base import Signal

# A signal source stays quiet for this many trading days after firing for
# a given ticker. Set equal to the report's default holding horizon (20
# trading days) — long enough that consecutive firings on the same rolling
# condition cannot share more than a sliver of their forward-return
# windows, short enough that a genuinely new event on the same ticker a
# month later is not suppressed.
MIN_SIGNAL_SPACING_DAYS = 20

# Below this, a gap is routine noise for anything but the most illiquid
# names. Above it, treated as "as dramatic as this asset class gets
# without being a halt or a delisting" and confidence caps out.
GAP_THRESHOLD = 0.03
GAP_FULL_CONFIDENCE_AT = 0.12

# Double the trailing 20-day average volume, scaling to "clearly
# something happened" at 6x.
REL_VOLUME_WINDOW = 20
REL_VOLUME_THRESHOLD = 2.0
REL_VOLUME_FULL_CONFIDENCE_AT = 6.0

MOMENTUM_20D_WINDOW = 20
MOMENTUM_20D_THRESHOLD = 0.05
MOMENTUM_20D_FULL_CONFIDENCE_AT = 0.25

MOMENTUM_60D_WINDOW = 60
MOMENTUM_60D_THRESHOLD = 0.10
MOMENTUM_60D_FULL_CONFIDENCE_AT = 0.40

REVERSAL_5D_WINDOW = 5
REVERSAL_5D_THRESHOLD = 0.08
REVERSAL_5D_FULL_CONFIDENCE_AT = 0.20

# (direction, confidence, extra evidence fields) or None if the feature
# didn't cross its threshold at bar i.
Detection = tuple[str, float, dict] | None
Detector = Callable[[list[Bar], int], Detection]


def _scale_confidence(magnitude: float, floor: float, full_at: float) -> float:
    """Confidence rises from 0.2 at the firing threshold to 0.8 at
    `full_at` and beyond, capped at 1.0 — the same "floor for firing at
    all, scaling toward a ceiling" shape used by every confidence formula
    elsewhere in this codebase (see `topos/signals/congress.py`,
    `topos/signals/form4.py`, `topos/signals/technical.py`)."""
    if full_at <= floor:
        return 0.8
    scaled = (magnitude - floor) / (full_at - floor)
    return max(0.0, min(1.0, 0.2 + max(0.0, min(scaled, 1.0)) * 0.6))


def _detect_gap(bars: list[Bar], i: int) -> Detection:
    gap = gap_pct(bars, i)
    if gap is None or abs(gap) < GAP_THRESHOLD:
        return None
    direction = "buy" if gap > 0 else "sell"
    confidence = _scale_confidence(abs(gap), GAP_THRESHOLD, GAP_FULL_CONFIDENCE_AT)
    return direction, confidence, {"gap_pct": round(gap, 4)}


def _detect_rel_volume(bars: list[Bar], i: int) -> Detection:
    rv = relative_volume(bars, i, window=REL_VOLUME_WINDOW)
    if rv is None or rv < REL_VOLUME_THRESHOLD or i < 1:
        return None
    prev_close = bars[i - 1].close
    if prev_close <= 0:
        return None
    day_return = (bars[i].close - prev_close) / prev_close
    if day_return == 0:
        return None  # a flat day carries no directional information
    direction = "buy" if day_return > 0 else "sell"
    confidence = _scale_confidence(rv, REL_VOLUME_THRESHOLD, REL_VOLUME_FULL_CONFIDENCE_AT)
    return direction, confidence, {
        "relative_volume": round(rv, 2),
        "day_return_pct": round(day_return, 4),
    }


def _make_momentum_detector(window: int, threshold: float, full_at: float) -> Detector:
    def detect(bars: list[Bar], i: int) -> Detection:
        trend = trailing_return(bars, i, window)
        if trend is None or abs(trend) < threshold:
            return None
        # Continuation: the direction the trend is already moving.
        direction = "buy" if trend > 0 else "sell"
        confidence = _scale_confidence(abs(trend), threshold, full_at)
        return direction, confidence, {f"trailing_return_{window}d": round(trend, 4)}

    return detect


def _detect_reversal(bars: list[Bar], i: int) -> Detection:
    move = trailing_return(bars, i, REVERSAL_5D_WINDOW)
    if move is None or abs(move) < REVERSAL_5D_THRESHOLD:
        return None
    # Contrarian: the opposite of momentum's convention, deliberately.
    direction = "sell" if move > 0 else "buy"
    confidence = _scale_confidence(abs(move), REVERSAL_5D_THRESHOLD, REVERSAL_5D_FULL_CONFIDENCE_AT)
    return direction, confidence, {"trailing_return_5d": round(move, 4)}


SOURCES: dict[str, Detector] = {
    "price_gap": _detect_gap,
    "price_rel_volume": _detect_rel_volume,
    "price_momentum_20d": _make_momentum_detector(
        MOMENTUM_20D_WINDOW, MOMENTUM_20D_THRESHOLD, MOMENTUM_20D_FULL_CONFIDENCE_AT
    ),
    "price_momentum_60d": _make_momentum_detector(
        MOMENTUM_60D_WINDOW, MOMENTUM_60D_THRESHOLD, MOMENTUM_60D_FULL_CONFIDENCE_AT
    ),
    "price_reversal_5d": _detect_reversal,
}


def _walk_with_cooldown(
    bars: list[Bar],
    *,
    source: str,
    ticker: str,
    detect: Detector,
    cooldown_days: int = MIN_SIGNAL_SPACING_DAYS,
) -> list[Signal]:
    """One source's signals across a ticker's whole stored history.

    `cooldown_days` after a firing is enforced regardless of how long the
    underlying condition stays true — see the module docstring for why a
    rolling feature needs this and a discrete filing does not.
    """
    signals: list[Signal] = []
    last_fired = -cooldown_days - 1  # so a firing on bar 0 is never suppressed
    for i in range(len(bars)):
        if i - last_fired < cooldown_days:
            continue
        detection = detect(bars, i)
        if detection is None:
            continue
        direction, confidence, extra = detection
        event_date = bars[i].date
        signals.append(
            Signal(
                timestamp=datetime.now(timezone.utc),
                event_date=event_date,
                # Deterministic and source-scoped, matching
                # topos/signals/technical.py's convention — recomputing
                # the same bar's features must not stack duplicate rows,
                # and since this whole computation is pure and DB-free,
                # re-running the backfill reproduces identical keys.
                dedup_key=f"{source}:{ticker}:{event_date.isoformat()}",
                source=source,
                ticker=ticker,
                confidence=round(confidence, 3),
                evidence={"direction": direction, **extra},
            )
        )
        last_fired = i
    return signals


def generate_price_action_signals(ticker: str, bars: list[Bar]) -> list[Signal]:
    """Every price-action signal this ticker's stored history supports,
    across all five sources. `bars` must be ordered oldest first, as
    `get_bars()` already returns them."""
    signals: list[Signal] = []
    for source, detect in SOURCES.items():
        signals.extend(
            _walk_with_cooldown(bars, source=source, ticker=ticker, detect=detect)
        )
    return signals
