from topos.portfolio.decision import TargetPosition
from topos.portfolio.rebalancer import Rebalancer


def test_rebalancer_buys_only_the_delta_not_full_weight_again():
    """The core fix: a ticker already held at its target weight should not
    generate another full-weight buy order on the next run."""
    targets = [TargetPosition(ticker="AAPL", weight=0.2, score=0.9)]
    current_positions = {"AAPL": 20_000.0}  # already at 20% of $100k equity

    orders = Rebalancer().plan(targets, current_positions, equity=100_000.0)

    assert orders == []


def test_rebalancer_buys_the_remaining_delta_when_underweight():
    targets = [TargetPosition(ticker="AAPL", weight=0.2, score=0.9)]
    current_positions = {"AAPL": 5_000.0}

    orders = Rebalancer().plan(targets, current_positions, equity=100_000.0)

    assert len(orders) == 1
    assert orders[0].ticker == "AAPL"
    assert orders[0].side == "buy"
    assert orders[0].notional_usd == 15_000.0


def test_rebalancer_trims_overweight_positions():
    targets = [TargetPosition(ticker="AAPL", weight=0.1, score=0.9)]
    current_positions = {"AAPL": 30_000.0}

    orders = Rebalancer().plan(targets, current_positions, equity=100_000.0)

    assert len(orders) == 1
    assert orders[0].side == "sell"
    assert orders[0].notional_usd == 20_000.0


def test_rebalancer_sells_positions_dropped_from_target_list():
    current_positions = {"OLD": 10_000.0}

    orders = Rebalancer().plan([], current_positions, equity=100_000.0)

    assert len(orders) == 1
    assert orders[0].ticker == "OLD"
    assert orders[0].side == "sell"
    assert orders[0].notional_usd == 10_000.0


def test_rebalancer_ignores_sub_threshold_deltas():
    targets = [TargetPosition(ticker="AAPL", weight=0.2, score=0.9)]
    current_positions = {"AAPL": 19_990.0}

    orders = Rebalancer(min_order_usd=25.0).plan(targets, current_positions, equity=100_000.0)

    assert orders == []
