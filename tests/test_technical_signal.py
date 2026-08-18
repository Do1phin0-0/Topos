from topos.signals.technical import TechnicalSignalExtractor, _rsi, _sma


def test_rsi_pins_to_extremes_on_pure_trends():
    uptrend = [100 + i for i in range(60)]
    downtrend = [200 - i for i in range(60)]

    assert _rsi(uptrend) == 100.0
    assert _rsi(downtrend) == 0.0


def test_score_returns_none_without_enough_history():
    assert TechnicalSignalExtractor()._score("TEST", [1.0, 2.0]) is None


def test_score_overbought_rsi_gives_contrarian_sell():
    uptrend = [100 + i for i in range(60)]

    signal = TechnicalSignalExtractor()._score("TEST", uptrend)

    assert signal.evidence["direction"] == "sell"
    assert signal.evidence["rsi_14"] >= 70


def test_score_oversold_rsi_gives_contrarian_buy():
    downtrend = [200 - i for i in range(60)]

    signal = TechnicalSignalExtractor()._score("TEST", downtrend)

    assert signal.evidence["direction"] == "buy"
    assert signal.evidence["rsi_14"] <= 30


def test_score_neutral_rsi_falls_back_to_sma_crossover():
    closes = [100.0]
    for i in range(59):
        closes.append(closes[-1] + (1.0 if i % 2 == 0 else -0.95))

    signal = TechnicalSignalExtractor()._score("TEST", closes)

    assert signal is not None
    assert 30 < signal.evidence["rsi_14"] < 70
    expected_direction = "buy" if signal.evidence["crossover"] == "bullish" else "sell"
    assert signal.evidence["direction"] == expected_direction


def test_sma_requires_full_window():
    assert _sma([1.0, 2.0, 3.0], 5) is None
    assert _sma([1.0, 2.0, 3.0], 3) == 2.0
