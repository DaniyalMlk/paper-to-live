"""Stage four: the cost of the capital."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest
from tenor import Compounding

from paper_to_live.execution import run_execution
from paper_to_live.funding import build_curve, run_funding, screen_for
from paper_to_live.selection import run_selection
from paper_to_live.types import PERIODS_PER_YEAR, Settings


@pytest.fixture(scope="module")
def net() -> np.ndarray:
    settings = Settings()
    return run_execution(settings, run_selection(settings)).net_returns


def test_the_curve_reprices_what_it_was_built_from() -> None:
    """A curve that does not reprice its own inputs is not a curve.

    This is a gate, not a diagnostic: every number this stage produces is read
    off the curve, so if the bootstrap did not converge the financing rate is
    arbitrary and the Sharpe ratio built on it is too.
    """
    curve = build_curve(Settings())
    assert curve.worst_error < 1e-12
    assert curve.reprices


def test_the_screen_is_well_formed_at_any_valuation_date() -> None:
    """Tenors are offsets, so the screen does not rot when the date moves."""
    for reference in (date(2019, 3, 1), date(2021, 1, 5), date(2026, 11, 30)):
        instruments = screen_for(reference)
        assert len(instruments) == 4
        curve = build_curve(Settings(valuation_date=reference))
        assert curve.worst_error < 1e-12


def test_the_discount_factor_and_the_zero_rate_are_the_same_statement() -> None:
    """Checked by hand rather than taken from the same accessor twice.

    A continuously compounded zero rate `z` at time `t` means a discount
    factor of `exp(-z t)`. If these two ever disagreed, one of them would be
    quoted in a convention the other is not, which is the single easiest way
    to be wrong by a factor of a hundred in fixed income.
    """
    result = run_funding(Settings(), np.full(1008, 0.0004))
    import math

    implied = math.exp(-result.zero_rate * result.horizon_years)
    assert result.discount_factor == pytest.approx(implied, rel=1e-12)


def test_funding_is_read_at_the_horizon_the_backtest_covers(
    net: np.ndarray,
) -> None:
    """A four-year holding funds at the four-year point, not overnight."""
    result = run_funding(Settings(), net)
    assert result.horizon_years == pytest.approx(net.size / PERIODS_PER_YEAR)

    curve = build_curve(Settings())
    expected = curve.curve.zero_rate_at(result.horizon_years, Compounding.CONTINUOUS)
    assert result.zero_rate == pytest.approx(expected, rel=1e-15)


def test_an_upward_curve_charges_a_longer_backtest_more(net: np.ndarray) -> None:
    """The screen rises with tenor, so the hurdle must rise with the horizon."""
    short = run_funding(Settings(), net[:252])
    long = run_funding(Settings(), net)
    assert long.zero_rate > short.zero_rate


def test_the_hurdle_accounts_for_the_whole_difference(net: np.ndarray) -> None:
    """Excess Sharpe is net Sharpe less the hurdle, exactly.

    Both are the same financing rate over the same volatility, so the
    decomposition is an identity. Asserting it is how a sign error or a
    double-annualisation in either term gets caught: each number alone would
    still look plausible.
    """
    result = run_funding(Settings(), net)
    assert result.net_sharpe_annual - result.hurdle_sharpe == pytest.approx(
        result.excess_sharpe_annual, rel=1e-12
    )


def test_a_zero_rate_curve_leaves_the_sharpe_alone() -> None:
    """The control that says the correction is the curve and nothing else."""
    import paper_to_live.funding as funding

    original = funding._QUOTES
    try:
        funding._QUOTES = tuple((kind, days, 0.0) for kind, days, _ in original)
        result = run_funding(Settings(), np.linspace(-0.01, 0.012, 1008))
        assert result.zero_rate == pytest.approx(0.0, abs=1e-15)
        assert result.hurdle_sharpe == pytest.approx(0.0, abs=1e-12)
        assert result.excess_sharpe_annual == pytest.approx(
            result.net_sharpe_annual, rel=1e-12
        )
    finally:
        funding._QUOTES = original


def test_funding_only_ever_lowers_a_sharpe_ratio(net: np.ndarray) -> None:
    result = run_funding(Settings(), net)
    assert result.excess_sharpe_annual < result.net_sharpe_annual
    assert result.hurdle_sharpe > 0.0


def test_a_series_too_short_for_a_sharpe_ratio_is_refused() -> None:
    with pytest.raises(ValueError, match="two observations"):
        run_funding(Settings(), np.array([0.01]))
