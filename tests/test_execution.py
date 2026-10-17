"""Stage two: what the strategy's trades cost."""

from __future__ import annotations

import numpy as np
import pytest
from slippage import ExecutionProblem, LinearImpact, SquareRootLaw, optimal_trajectory

from paper_to_live.execution import annual_drag_on_sharpe, run_execution
from paper_to_live.selection import SelectionResult, run_selection
from paper_to_live.types import Settings, to_bps

Fixture = tuple[Settings, SelectionResult]


@pytest.fixture(scope="module")
def default() -> Fixture:
    settings = Settings()
    return settings, run_selection(settings)


def test_every_position_change_becomes_an_order(default: Fixture) -> None:
    """No trade is free and none is missed.

    The count is the number of days the holding moved plus the final unwind:
    the book starts flat and ends flat, and charging for neither end would
    hand the strategy a free round trip.
    """
    settings, selection = default
    result = run_execution(settings, selection)
    assert len(result.orders) == selection.position_changes + 1


def test_a_reversal_trades_twice_the_book(default: Fixture) -> None:
    """Long to short is two units of notional, not one."""
    settings, selection = default
    result = run_execution(settings, selection)
    reversals = [
        order for order in result.orders if order.quantity > 1.5 * settings.notional
    ]
    assert reversals, "a long/short crossover rule must reverse at some point"
    for order in reversals:
        assert order.quantity == pytest.approx(2 * settings.notional)


def test_the_risk_neutral_trajectory_agrees_with_the_law() -> None:
    """The schedule and the charge describe the same market.

    Almgren-Chriss is solved in closed form only for linear impact, while the
    cost this stage charges comes from the square-root law. The linear
    coefficient is fitted so the two agree at the order being scheduled, which
    makes this an identity rather than an approximation: with no permanent
    impact and no risk aversion, the trajectory's cost is what the law charges.

    Checked here rather than trusted, because a mismatch would mean the
    picture of the execution and the number charged for it came from two
    different models.
    """
    quantity, volume, volatility = 100e6, 300e6, 0.0065
    law = SquareRootLaw(y=0.8, delta=0.5)
    charged = law.expected_cost(quantity, volume, volatility)
    eta = charged / quantity

    problem = ExecutionProblem(
        quantity=quantity,
        horizon=1.0,
        periods=26,
        volatility=volatility,
        impact=LinearImpact(gamma=0.0, eta=eta),
    )
    trajectory = optimal_trajectory(problem, risk_aversion=0.0)
    assert trajectory.expected_cost / quantity == pytest.approx(charged, rel=1e-12)


def test_risk_aversion_front_loads_and_pays_for_it(default: Fixture) -> None:
    """Trading sooner costs more impact and carries less price risk.

    Both halves are asserted. A schedule that front-loads without paying more
    would mean the cost model had stopped responding to the rate, and a
    schedule that pays more without front-loading would mean the optimiser had.
    """
    settings, selection = default
    result = run_execution(settings, selection)
    schedule = result.representative
    assert schedule is not None
    assert schedule.front_loading > 0.5

    law = SquareRootLaw(y=settings.impact_y, delta=0.5)
    volatility = float(np.std(selection.market, ddof=1))
    neutral = to_bps(
        law.expected_cost(schedule.quantity, settings.daily_volume, volatility)
    )
    assert schedule.expected_cost_bps > neutral


def test_cost_is_charged_and_the_series_moves(default: Fixture) -> None:
    """Net returns are below gross on trading days and equal on the rest."""
    settings, selection = default
    result = run_execution(settings, selection)
    difference = selection.returns - result.net_returns
    assert np.all(difference >= -1e-15)
    charged_days = int(np.count_nonzero(difference > 0))
    assert 0 < charged_days <= len(result.orders)


def test_cost_grows_with_size_and_shrinks_with_volume(default: Fixture) -> None:
    """The order as a fraction of volume is what sets the cost.

    Doubling the capital on the same instrument is not the same decision as
    trading the same capital in a market twice as deep, and the drag has to
    move the right way for each.
    """
    settings, selection = default
    base = run_execution(settings, selection).annual_cost_bps
    bigger = run_execution(
        Settings(notional=2 * settings.notional), selection
    ).annual_cost_bps
    deeper = run_execution(
        Settings(daily_volume=4 * settings.daily_volume), selection
    ).annual_cost_bps
    assert bigger > base
    assert deeper < base


def test_the_square_root_law_halves_cost_for_a_quarter_of_the_size() -> None:
    """The exponent is the claim, so it is measured rather than described."""
    law = SquareRootLaw(y=0.8, delta=0.5)
    big = law.expected_cost(100e6, 300e6, 0.0065)
    small = law.expected_cost(25e6, 300e6, 0.0065)
    assert big / small == pytest.approx(2.0, rel=1e-12)


def test_quoting_the_peak_would_overstate_the_bill(default: Fixture) -> None:
    """Under the square root the average paid is two thirds of the peak.

    So the overstatement is half of what was actually paid. Published impact
    coefficients are peaks, which makes this the easiest way to be wrong by
    fifty per cent while quoting a real number.
    """
    settings, selection = default
    result = run_execution(settings, selection)
    assert result.peak_vs_average_bps == pytest.approx(
        0.5 * result.total_cost_bps, rel=1e-9
    )


def test_execution_cannot_improve_a_strategy(default: Fixture) -> None:
    settings, selection = default
    result = run_execution(settings, selection)
    assert result.net_sharpe_annual < result.gross_sharpe_annual
    assert annual_drag_on_sharpe(result) > 0.0


def test_a_strategy_that_never_trades_costs_nothing(default: Fixture) -> None:
    """A degenerate control, so the cost is known to come from the trades.

    Holding nothing at all sends no orders, which also exercises the branch
    where there is no largest order to draw a trajectory for.
    """
    settings, selection = default
    from dataclasses import replace

    flat = replace(
        selection,
        positions=np.zeros_like(selection.positions),
        returns=np.zeros_like(selection.returns),
    )
    result = run_execution(settings, flat)
    assert result.orders == ()
    assert result.total_cost_bps == 0.0
    assert result.representative is None
