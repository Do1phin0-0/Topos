from datetime import date, timedelta

import pytest

from topos.analysis.price_features import gap_pct, relative_volume, trailing_return
from topos.collectors.prices import Bar

_START = date(2026, 1, 1)


def _bars(closes, opens=None, volumes=None):
    opens = opens or closes
    volumes = volumes or [1_000_000.0] * len(closes)
    return [
        Bar(date=_START + timedelta(days=i), open=o, high=max(o, c), low=min(o, c), close=c, volume=v)
        for i, (o, c, v) in enumerate(zip(opens, closes, volumes))
    ]


def test_gap_pct_measures_open_versus_prior_close():
    bars = _bars(closes=[100, 100], opens=[100, 106])
    assert gap_pct(bars, 1) == pytest.approx(0.06)


def test_gap_pct_none_on_first_bar():
    bars = _bars(closes=[100])
    assert gap_pct(bars, 0) is None


def test_gap_pct_none_on_non_positive_prior_close():
    bars = _bars(closes=[0, 100])
    assert gap_pct(bars, 1) is None


def test_gap_pct_ignores_bars_after_i():
    # Same history through bar 1; what happens at bar 2 must not change
    # what gap_pct(bars, 1) reports.
    short = _bars(closes=[100, 100], opens=[100, 106])
    long_ = _bars(closes=[100, 100, 500], opens=[100, 106, 1])
    assert gap_pct(short, 1) == gap_pct(long_, 1)


def test_relative_volume_excludes_the_bar_itself_from_its_baseline():
    closes = [100.0] * 21
    volumes = [1_000_000.0] * 20 + [5_000_000.0]
    bars = _bars(closes=closes, volumes=volumes)
    assert relative_volume(bars, 20) == pytest.approx(5.0)


def test_relative_volume_none_before_full_window():
    bars = _bars(closes=[100.0] * 10)
    assert relative_volume(bars, 5, window=20) is None


def test_relative_volume_none_on_non_positive_baseline():
    bars = _bars(closes=[100.0] * 21, volumes=[0.0] * 20 + [1_000_000.0])
    assert relative_volume(bars, 20) is None


def test_trailing_return_measures_the_trend_up_to_and_including_i():
    closes = [100.0, 105.0, 110.0]
    bars = _bars(closes=closes)
    assert trailing_return(bars, 2, window=2) == pytest.approx(0.10)


def test_trailing_return_none_without_full_window():
    bars = _bars(closes=[100.0, 101.0])
    assert trailing_return(bars, 1, window=5) is None


def test_trailing_return_none_on_non_positive_start():
    bars = _bars(closes=[0.0, 100.0])
    assert trailing_return(bars, 1, window=1) is None
