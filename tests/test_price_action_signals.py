from datetime import date, timedelta

import pytest

from topos.collectors.prices import Bar
from topos.signals.price_action import (
    MOMENTUM_20D_FULL_CONFIDENCE_AT,
    MOMENTUM_20D_THRESHOLD,
    MOMENTUM_20D_WINDOW,
    REVERSAL_5D_WINDOW,
    _detect_gap,
    _detect_rel_volume,
    _detect_reversal,
    _make_momentum_detector,
    _walk_with_cooldown,
    generate_price_action_signals,
)

_START = date(2026, 1, 1)


def _bars(closes, opens=None, volumes=None):
    opens = opens or closes
    volumes = volumes or [1_000_000.0] * len(closes)
    return [
        Bar(date=_START + timedelta(days=i), open=o, high=max(o, c), low=min(o, c), close=c, volume=v)
        for i, (o, c, v) in enumerate(zip(opens, closes, volumes))
    ]


def test_detect_gap_fires_on_large_up_gap():
    bars = _bars(closes=[100, 100], opens=[100, 106])
    direction, confidence, evidence = _detect_gap(bars, 1)
    assert direction == "buy"
    assert evidence["gap_pct"] == pytest.approx(0.06)
    assert 0.2 <= confidence <= 0.8


def test_detect_gap_ignores_small_moves():
    bars = _bars(closes=[100, 100], opens=[100, 101])  # 1% gap, below threshold
    assert _detect_gap(bars, 1) is None


def test_detect_gap_direction_follows_gap_sign():
    down = _bars(closes=[100, 100], opens=[100, 94])
    direction, _, _ = _detect_gap(down, 1)
    assert direction == "sell"


def test_detect_gap_never_sees_future_bars():
    short = _bars(closes=[100, 100], opens=[100, 106])
    long_ = _bars(closes=[100, 100, 200], opens=[100, 106, 50])
    assert _detect_gap(short, 1) == _detect_gap(long_, 1)


def test_detect_rel_volume_fires_on_spike_and_takes_direction_from_day_return():
    closes = [100.0] * 20 + [103.0]
    volumes = [1_000_000.0] * 20 + [5_000_000.0]
    bars = _bars(closes=closes, volumes=volumes)
    direction, confidence, evidence = _detect_rel_volume(bars, 20)
    assert direction == "buy"
    assert evidence["relative_volume"] == pytest.approx(5.0)


def test_detect_rel_volume_requires_the_threshold():
    closes = [100.0] * 21
    volumes = [1_000_000.0] * 20 + [1_500_000.0]  # 1.5x, below the 2.0 threshold
    bars = _bars(closes=closes, volumes=volumes)
    assert _detect_rel_volume(bars, 20) is None


def test_detect_rel_volume_skips_a_flat_day():
    # Volume spikes but price doesn't move — no directional claim to make.
    closes = [100.0] * 21
    volumes = [1_000_000.0] * 20 + [5_000_000.0]
    bars = _bars(closes=closes, volumes=volumes)
    assert _detect_rel_volume(bars, 20) is None


def test_momentum_detector_bets_on_continuation():
    closes = [100 + i for i in range(21)]  # steady uptrend, +20%
    bars = _bars(closes=closes)
    detect = _make_momentum_detector(
        MOMENTUM_20D_WINDOW, MOMENTUM_20D_THRESHOLD, MOMENTUM_20D_FULL_CONFIDENCE_AT
    )
    direction, confidence, evidence = detect(bars, 20)
    assert direction == "buy"
    assert evidence["trailing_return_20d"] == pytest.approx(0.20)


def test_momentum_detector_requires_the_threshold():
    closes = [100 + i * 0.1 for i in range(21)]  # a 2.1% trend, below 5%
    bars = _bars(closes=closes)
    detect = _make_momentum_detector(
        MOMENTUM_20D_WINDOW, MOMENTUM_20D_THRESHOLD, MOMENTUM_20D_FULL_CONFIDENCE_AT
    )
    assert detect(bars, 20) is None


def test_reversal_detector_bets_against_a_sharp_drop():
    closes = [100, 100, 100, 100, 100, 90]  # -10% over 5 days
    bars = _bars(closes=closes)
    direction, confidence, evidence = _detect_reversal(bars, REVERSAL_5D_WINDOW)
    assert direction == "buy"  # bounce, opposite of momentum's convention


def test_reversal_detector_bets_against_a_sharp_rise():
    closes = [100, 100, 100, 100, 100, 110]  # +10% over 5 days
    bars = _bars(closes=closes)
    direction, confidence, evidence = _detect_reversal(bars, REVERSAL_5D_WINDOW)
    assert direction == "sell"  # pullback


def test_cooldown_suppresses_repeated_firings_within_the_window():
    n = 30
    closes = [100.0] * n
    opens = [100.0] * n
    opens[1] = 106.0
    opens[5] = 106.0  # inside the cooldown following bar 1
    opens[25] = 106.0  # outside a 20-trading-day cooldown
    bars = _bars(closes=closes, opens=opens)

    signals = _walk_with_cooldown(bars, source="price_gap", ticker="TEST", detect=_detect_gap)

    assert [s.event_date for s in signals] == [bars[1].date, bars[25].date]


def test_dedup_key_is_deterministic_across_reruns():
    bars = _bars(closes=[100, 100], opens=[100, 106])
    first = generate_price_action_signals("TEST", bars)
    second = generate_price_action_signals("TEST", bars)
    assert [s.dedup_key for s in first] == [s.dedup_key for s in second]
    assert all(s.dedup_key.startswith("price_gap:TEST:") for s in first)


def test_generate_price_action_signals_covers_momentum_sources_given_a_sustained_trend():
    closes = [100 + i * 0.5 for i in range(70)]
    bars = _bars(closes=closes)
    signals = generate_price_action_signals("TEST", bars)
    sources = {s.source for s in signals}
    assert "price_momentum_20d" in sources
    assert "price_momentum_60d" in sources
