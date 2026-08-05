"""The price collector has to survive a source dying mid-run.

This happened for real: Stooq answered 404 for AAPL and ADBE alongside
DNS failures and timeouts, and a 250-ticker backfill spent fifteen
minutes rediscovering the same dead host, storing zero bars. The chain
exists so one broken source degrades to the next one — and so a host
that is not answering stops being asked.
"""

from datetime import date

import pytest
import requests

from topos.collectors.prices import (
    BENCH_AFTER,
    Bar,
    PriceCollector,
    parse_yahoo_chart,
)

_BAR = Bar(date=date(2026, 1, 5), open=10, high=11, low=9, close=10.5, volume=2e6)


class _Source:
    """A scriptable stand-in: each behavior is either bars to return or
    an exception to raise, consumed one per call."""

    def __init__(self, name, behaviors):
        self.name = name
        self.behaviors = list(behaviors)
        self.calls = 0

    def daily_bars(self, ticker):
        self.calls += 1
        behavior = self.behaviors.pop(0) if self.behaviors else []
        if isinstance(behavior, Exception):
            raise behavior
        return behavior


# --- the fallback chain ----------------------------------------------


def test_second_source_answers_when_the_first_has_no_data():
    chain = PriceCollector(sources=[_Source("a", [[]]), _Source("b", [[_BAR]])])

    assert chain.daily_bars("AAPL") == [_BAR]


def test_second_source_answers_when_the_first_errors():
    chain = PriceCollector(
        sources=[
            _Source("a", [requests.HTTPError("404")]),
            _Source("b", [[_BAR]]),
        ]
    )

    assert chain.daily_bars("AAPL") == [_BAR]


def test_first_source_is_preferred_while_it_works():
    second = _Source("b", [[_BAR]])
    chain = PriceCollector(sources=[_Source("a", [[_BAR]]), second])

    chain.daily_bars("AAPL")

    assert second.calls == 0


def test_a_source_that_cannot_connect_is_benched_not_retried_forever():
    # The expensive failure: each timeout costs its full 15 seconds. After
    # BENCH_AFTER of those in a row the source must stop being asked.
    dead = _Source("a", [requests.ConnectTimeout("dead")] * 10)
    alive = _Source("b", [[_BAR]] * 10)
    chain = PriceCollector(sources=[dead, alive])

    for _ in range(6):
        assert chain.daily_bars("AAPL") == [_BAR]

    assert dead.calls == BENCH_AFTER


def test_http_rejections_do_not_bench_a_source():
    # 404s are cheap and can legitimately differ per ticker; a source
    # must not be written off for not knowing some symbols.
    flaky = _Source("a", [requests.HTTPError("404")] * 10)
    alive = _Source("b", [[_BAR]] * 10)
    chain = PriceCollector(sources=[flaky, alive])

    for _ in range(6):
        chain.daily_bars("AAPL")

    assert flaky.calls == 6


def test_one_success_resets_the_failure_count():
    # Two timeouts, a success, two timeouts: never BENCH_AFTER in a row,
    # so the source stays in play throughout.
    wobbling = _Source(
        "a",
        [
            requests.ConnectTimeout("x"),
            requests.ConnectTimeout("x"),
            [_BAR],
            requests.ConnectTimeout("x"),
            requests.ConnectTimeout("x"),
            [_BAR],
        ],
    )
    backup = _Source("b", [[_BAR]] * 10)
    chain = PriceCollector(sources=[wobbling, backup])

    for _ in range(6):
        assert chain.daily_bars("AAPL") == [_BAR]

    assert wobbling.calls == 6


def test_error_raised_only_when_every_source_failed():
    chain = PriceCollector(
        sources=[
            _Source("a", [requests.ConnectTimeout("dead")]),
            _Source("b", [requests.HTTPError("503")]),
        ]
    )

    with pytest.raises(requests.RequestException):
        chain.daily_bars("AAPL")


def test_no_data_anywhere_is_an_empty_answer_not_an_error():
    # 'No source knows this symbol' is a fact about the ticker, and the
    # backfill treats it as zero bars — not a crash.
    chain = PriceCollector(sources=[_Source("a", [[]]), _Source("b", [[]])])

    assert chain.daily_bars("XXNOPE") == []


# --- Yahoo parsing ----------------------------------------------------


def _payload(timestamps, opens, highs, lows, closes, volumes):
    return {
        "chart": {
            "result": [
                {
                    "timestamp": timestamps,
                    "indicators": {
                        "quote": [
                            {
                                "open": opens,
                                "high": highs,
                                "low": lows,
                                "close": closes,
                                "volume": volumes,
                            }
                        ]
                    },
                }
            ]
        }
    }


def test_yahoo_chart_parses_full_bars_oldest_first():
    # 2026-01-06 then 2026-01-05, deliberately out of order.
    bars = parse_yahoo_chart(
        _payload(
            [1767690000, 1767603600],
            [11.0, 10.0],
            [12.0, 11.0],
            [10.5, 9.5],
            [11.5, 10.5],
            [2e6, 3e6],
        )
    )

    assert [b.date for b in bars] == [date(2026, 1, 5), date(2026, 1, 6)]
    assert bars[0].close == 10.5


def test_yahoo_null_padded_rows_are_dropped_not_fabricated():
    bars = parse_yahoo_chart(
        _payload(
            [1767603600, 1767690000],
            [10.0, None],
            [11.0, None],
            [9.5, None],
            [10.5, None],
            [3e6, None],
        )
    )

    assert len(bars) == 1
    assert bars[0].date == date(2026, 1, 5)


def test_yahoo_error_payloads_yield_no_bars():
    assert parse_yahoo_chart({}) == []
    assert parse_yahoo_chart({"chart": {"result": None}}) == []
    assert parse_yahoo_chart({"chart": {"result": []}}) == []
