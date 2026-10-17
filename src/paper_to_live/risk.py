"""Stage three: what the book risks once it is on.

A Sharpe ratio is a ratio of two moments and says nothing about the shape of
the loss that pays for them. Two strategies with the same mean and the same
standard deviation can have very different worst weeks, and the one a desk can
hold is decided by the worst week rather than by the ratio.

This stage reports value at risk and expected shortfall of the net series,
the drawdown it would have put an investor through, and — the part usually
left out — how much sample is actually behind the tail number. A 99% expected
shortfall taken from four years of daily data is an average over about ten
observations. That is a real estimate and it is not a precise one, and the
count is reported next to the number rather than in a footnote.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from shortfall import drawdown_series, historical_risk, longest_underwater

from .types import FloatArray, Settings, to_bps


@dataclass(frozen=True, slots=True)
class RiskResult:
    """The loss distribution of the net return series.

    Attributes
    ----------
    confidence
        The level the two tail numbers are taken at.
    value_at_risk_bps
        The loss the series exceeded on one day in a hundred, in basis points
        of capital. A threshold, not an expectation: it says where the tail
        starts and nothing about what is in it.
    expected_shortfall_bps
        The average loss on the days past that threshold. This is the number
        to hold a book against, because it is the only one of the two that
        changes when the tail gets worse.
    tail_observations
        How many days the shortfall was averaged over. Published beside the
        estimate because at a 99% level over a few years it is of order ten,
        and an average of ten numbers carries a standard error worth seeing.
    observations
        Length of the sample.
    max_drawdown
        Deepest fall below the running peak, as a fraction of the peak.
    longest_underwater_days
        Length of the longest run spent below a previous peak. An investor
        experiences this and not the Sharpe ratio: a strategy can be in the
        money on paper and still have been underwater for two years.
    recovered
        Whether that run ended inside the sample. ``False`` means the series
        finished below a peak it never got back to, so the figure above is a
        floor rather than a measurement.
    tail_ratio
        Expected shortfall divided by value at risk. Near one for a thin tail;
        further above it the more the loss beyond the threshold matters.
    """

    confidence: float
    value_at_risk_bps: float
    expected_shortfall_bps: float
    tail_observations: int
    observations: int
    max_drawdown: float
    longest_underwater_days: int
    recovered: bool
    tail_ratio: float


def run_risk(settings: Settings, net_returns: FloatArray) -> RiskResult:
    """Measure the loss distribution of a net return series."""
    series = [float(value) for value in net_returns]
    if not series:
        raise ValueError("cannot measure the risk of an empty return series")

    measured = historical_risk(series, confidence=settings.confidence)
    drawdowns = drawdown_series(series)
    underwater = longest_underwater(series)

    value_at_risk = measured.value_at_risk
    ratio = (
        measured.expected_shortfall / value_at_risk
        if value_at_risk > 0.0
        else float("nan")
    )
    return RiskResult(
        confidence=settings.confidence,
        value_at_risk_bps=to_bps(value_at_risk),
        expected_shortfall_bps=to_bps(measured.expected_shortfall),
        tail_observations=measured.tail_observations,
        observations=measured.observations,
        max_drawdown=float(np.max(drawdowns)) if drawdowns else 0.0,
        longest_underwater_days=int(underwater.underwater_periods),
        recovered=bool(underwater.recovered),
        tail_ratio=float(ratio),
    )


def risk_adjusted_capital(result: RiskResult, multiple: float = 3.0) -> float:
    """Capital a desk would hold against this book, as a fraction of notional.

    A common rule of thumb rather than a regulatory figure: enough to absorb
    some multiple of the one-day expected shortfall. It is here so the risk
    numbers connect to something a reader can act on, and the multiple is an
    argument because the rule is a convention and not a result.
    """
    if multiple <= 0.0:
        raise ValueError(f"multiple must be positive, got {multiple!r}")
    return multiple * result.expected_shortfall_bps / 10_000.0


__all__ = ["RiskResult", "risk_adjusted_capital", "run_risk"]
