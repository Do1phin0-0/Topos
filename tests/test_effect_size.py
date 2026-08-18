"""Significance is not size, and a big sample makes that dangerous.

The real report, on 11,348 observations, returned Spearman +0.020 with
p=0.031 and concluded "the ranking has directional validity", verdict
DECREASE, safe to act: **yes**. That correlation explains 0.04% of the
variation in returns. The guardrails were built to stop exactly this —
a number that is real, an edge that is not — and they missed it, because
every threshold in them was about sample size and none about magnitude.
"""

from topos.backtesting.research import (
    MIN_ACTIONABLE_CORRELATION,
    CohortComparison,
    CohortResult,
    CorrelationResult,
    weight_recommendation,
)


def _correlation(n: int, rho: float, p: float) -> CorrelationResult:
    return CorrelationResult(n=n, spearman=rho, pearson=rho, p_value=p, horizon_days=20)


def _cohorts(difference: float, p: float, n: int = 4000) -> CohortComparison:
    return CohortComparison(
        horizon_days=20,
        cohorts=[
            CohortResult("single-source", n, 0.005, 0.47),
            CohortResult("multi-source", n, -0.007, 0.45),
        ],
        p_value=p,
        difference=difference,
    )


# --- the verdict ------------------------------------------------------


def test_the_real_reports_numbers_are_not_called_directional_validity():
    # Spearman +0.020, p=0.031, n=11,348 — the actual 2026-08-07 run.
    result = _correlation(n=11348, rho=0.020, p=0.031)

    assert "NEGLIGIBLE" in result.verdict
    assert "0.04%" in result.verdict  # variance explained, spelled out
    assert "POSITIVE" not in result.verdict


def test_a_negligible_effect_is_distinguished_from_no_effect():
    # Different findings, different responses: one says look elsewhere,
    # the other says the effect is real and far too small to trade.
    negligible = _correlation(n=11348, rho=0.020, p=0.031)
    absent = _correlation(n=11348, rho=0.002, p=0.700)

    assert "NEGLIGIBLE" in negligible.verdict
    assert absent.verdict == "NO SIGNIFICANT RELATIONSHIP"


def test_an_effect_above_the_floor_is_still_reported_as_positive():
    result = _correlation(n=2000, rho=0.18, p=0.001)

    assert result.verdict.startswith("POSITIVE")


def test_the_floor_applies_to_negative_correlations_too():
    # A tiny negative is noise, not evidence of an inverted convention,
    # and must not trigger an investigation into a bug that isn't there.
    result = _correlation(n=11348, rho=-0.020, p=0.031)

    assert "NEGLIGIBLE" in result.verdict


def test_variance_explained_is_the_square_of_the_correlation():
    assert _correlation(n=100, rho=0.2, p=0.01).variance_explained == 0.04000000000000001


# --- the recommendation ----------------------------------------------


def test_a_negligible_correlation_never_authorises_acting():
    result = weight_recommendation(
        _correlation(n=11348, rho=0.020, p=0.031),
        _cohorts(-0.0123, 0.015),
        [],
    )

    assert result.verdict == "UNCHANGED"
    assert result.safe_to_act is False


def test_the_reason_explains_why_significance_was_not_enough():
    result = weight_recommendation(
        _correlation(n=11348, rho=0.020, p=0.031), _cohorts(-0.0123, 0.015), []
    )
    reason = " ".join(result.reasons)

    assert "significance is not size" in reason.lower()
    assert "0.04%" in reason


def test_a_significant_cohort_difference_cannot_override_a_negligible_score():
    # -1.23% at p=0.015 is a real magnitude, and it still does not make a
    # ρ=0.02 ranking safe to retune against.
    result = weight_recommendation(
        _correlation(n=11348, rho=0.020, p=0.031),
        _cohorts(-0.0123, 0.001),
        [],
    )

    assert result.verdict == "UNCHANGED"


def test_an_effect_clearing_the_floor_still_reaches_a_recommendation():
    # The guard must not have made the report incapable of ever saying
    # anything — a real effect on a real sample still gets through.
    result = weight_recommendation(
        _correlation(n=2000, rho=0.18, p=0.001), _cohorts(0.02, 0.01), []
    )

    assert result.verdict == "INCREASE"
    assert result.safe_to_act is True


def test_the_floor_sits_where_the_constant_says():
    just_under = _correlation(n=5000, rho=MIN_ACTIONABLE_CORRELATION - 0.001, p=0.01)
    just_over = _correlation(n=5000, rho=MIN_ACTIONABLE_CORRELATION + 0.001, p=0.01)

    assert "NEGLIGIBLE" in just_under.verdict
    assert just_over.verdict.startswith("POSITIVE")


# --- output has to survive the console it is read in ------------------


def test_every_verdict_string_is_printable_on_windows():
    """A Greek rho in the negligible verdict crashed the real run.

    `Path.write_text` defaults to the locale encoding; on Windows that is
    cp1252, which has no U+03C1, so the entire report was lost at the
    final write after all the analysis had already been done. The file is
    now written as UTF-8, but the strings themselves are kept inside
    cp1252 so a PowerShell `Get-Content` renders them rather than
    mangling them.
    """
    cases = [
        _correlation(n=11348, rho=0.020, p=0.031),   # NEGLIGIBLE
        _correlation(n=11348, rho=-0.020, p=0.031),  # NEGLIGIBLE, negative
        _correlation(n=2000, rho=0.18, p=0.001),     # POSITIVE
        _correlation(n=2000, rho=-0.18, p=0.001),    # NEGATIVE
        _correlation(n=11348, rho=0.002, p=0.700),   # NO SIGNIFICANT
        _correlation(n=5, rho=0.5, p=0.01),          # INSUFFICIENT
    ]

    for case in cases:
        case.verdict.encode("cp1252")


def test_every_recommendation_reason_is_printable_on_windows():
    for rho, p in [(0.020, 0.031), (0.18, 0.001), (-0.18, 0.001), (0.002, 0.700)]:
        result = weight_recommendation(
            _correlation(n=11348, rho=rho, p=p), _cohorts(-0.0123, 0.015), []
        )
        for reason in result.reasons:
            reason.encode("cp1252")
