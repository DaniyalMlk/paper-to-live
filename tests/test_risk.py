"""Stage three: the loss distribution of the net book."""

from __future__ import annotations

import math

import numpy as np
import pytest

from paper_to_live.execution import run_execution
from paper_to_live.risk import risk_adjusted_capital, run_risk
from paper_to_live.selection import run_selection
from paper_to_live.types import Settings


@pytest.fixture(scope="module")
def net() -> tuple[Settings, np.ndarray]:
    settings = Settings()
    selection = run_selection(settings)
    return settings, run_execution(settings, selection).net_returns


def test_shortfall_is_worse_than_value_at_risk(net: tuple[Settings, np.ndarray]) -> None:
    """An average of the tail cannot be milder than where the tail starts.

    True by construction, which is why it is worth asserting: if it ever
    failed, the two numbers would have come from different conventions — one
    a loss and the other a return, say — and every figure downstream of them
    would be wrong in a way nothing else would catch.
    """
    settings, series = net
    result = run_risk(settings, series)
    assert result.expected_shortfall_bps > result.value_at_risk_bps
    assert result.tail_ratio > 1.0


def test_the_tail_sample_is_small_and_says_so(net: tuple[Settings, np.ndarray]) -> None:
    """The count behind a 99% shortfall is of order ten, and is reported.

    This is the number that keeps the estimate honest. Four years of daily
    data past a 99% threshold is about ten observations, so the shortfall is
    an average of ten numbers and carries the standard error of one.
    """
    settings, series = net
    result = run_risk(settings, series)
    assert result.observations == series.size
    assert result.tail_observations == pytest.approx(
        series.size * (1 - settings.confidence), abs=3
    )
    assert result.tail_observations < 20


def test_a_lower_confidence_level_gives_a_milder_and_better_measured_tail(
    net: tuple[Settings, np.ndarray],
) -> None:
    settings, series = net
    strict = run_risk(settings, series)
    loose = run_risk(Settings(confidence=0.95), series)
    assert loose.expected_shortfall_bps < strict.expected_shortfall_bps
    assert loose.tail_observations > strict.tail_observations


def test_a_normal_sample_reproduces_its_known_shortfall() -> None:
    """Calibration against a case with a closed form.

    For a standard normal the 99% expected shortfall is the density at the
    quantile divided by the tail probability, which is 2.665. Drawing enough
    samples to recover it to two decimal places is the check that the
    estimator is the quantity it claims to be and not something adjacent.
    """
    rng = np.random.default_rng(0)
    sample = rng.standard_normal(400_000)
    quantile = 2.3263478740408408  # the 99th percentile of a standard normal
    closed_form = math.exp(-(quantile**2) / 2) / math.sqrt(2 * math.pi) / 0.01

    result = run_risk(Settings(confidence=0.99), sample)
    assert result.expected_shortfall_bps / 10_000.0 == pytest.approx(
        closed_form, rel=0.02
    )
    assert result.value_at_risk_bps / 10_000.0 == pytest.approx(quantile, rel=0.02)


def test_drawdown_is_bounded_and_deeper_than_a_single_day(
    net: tuple[Settings, np.ndarray],
) -> None:
    settings, series = net
    result = run_risk(settings, series)
    assert 0.0 < result.max_drawdown < 1.0
    assert result.max_drawdown > result.value_at_risk_bps / 10_000.0
    assert result.longest_underwater_days > 0


def test_a_rising_series_never_goes_underwater() -> None:
    """A control: the drawdown numbers come from the losses, not the length."""
    result = run_risk(Settings(confidence=0.95), np.full(500, 0.001))
    assert result.max_drawdown == 0.0
    assert result.longest_underwater_days == 0


def test_an_empty_series_is_refused() -> None:
    with pytest.raises(ValueError, match="empty"):
        run_risk(Settings(), np.array([], dtype=np.float64))


def test_capital_scales_with_the_multiple(net: tuple[Settings, np.ndarray]) -> None:
    settings, series = net
    result = run_risk(settings, series)
    assert risk_adjusted_capital(result, 6.0) == pytest.approx(
        2 * risk_adjusted_capital(result, 3.0)
    )
    with pytest.raises(ValueError, match="positive"):
        risk_adjusted_capital(result, 0.0)
