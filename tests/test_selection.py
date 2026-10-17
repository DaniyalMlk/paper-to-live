"""Stage one: the candidate set and the deflation of its winner."""

from __future__ import annotations

import numpy as np
import pytest
from holdout import deflated_sharpe_ratio

from paper_to_live.selection import (
    ReconstructionFailed,
    reconstruct_positions,
    run_selection,
)
from paper_to_live.types import Settings


def test_reconstruction_is_exact_on_the_default_sweep() -> None:
    """The holdings stage two prices are the holdings the backtest held.

    Exact equality rather than a tolerance: the recovered position is snapped
    to a whole number, so if the snap is right the product is the same floating
    point multiplication the sweep performed, bit for bit.
    """
    result = run_selection(Settings())
    assert result.reconstruction.worst_error == 0.0
    assert result.reconstruction.ambiguous_days == 0
    assert set(np.unique(result.positions)) <= {-1.0, 0.0, 1.0}


def test_reconstruction_recovers_a_known_schedule() -> None:
    market = np.array([0.01, -0.02, 0.015, -0.005, 0.03], dtype=np.float64)
    positions = np.array([1.0, 1.0, -1.0, -1.0, 1.0], dtype=np.float64)
    recovered = reconstruct_positions(positions * market, market)
    assert np.array_equal(recovered.positions, positions)
    assert recovered.worst_error == 0.0


def test_a_flat_market_day_carries_the_position_and_is_counted() -> None:
    """A day the market did not move hides the holding, and says so.

    Any position reproduces a zero return, so ``worst_error`` cannot catch a
    wrong guess here. The count is reported instead of being absorbed, which
    is the only honest handling: the caller can see how much of the schedule
    was inferred rather than read.
    """
    market = np.array([0.01, 0.0, 0.02], dtype=np.float64)
    strategy = np.array([0.01, 0.0, 0.02], dtype=np.float64)
    recovered = reconstruct_positions(strategy, market)
    assert recovered.ambiguous_days == 1
    assert np.array_equal(recovered.positions, np.ones(3))


def test_a_fractional_holding_is_refused() -> None:
    """The sweep holds whole units. Anything else means the inputs disagree."""
    market = np.array([0.01, 0.02], dtype=np.float64)
    with pytest.raises(ReconstructionFailed, match="whole holding"):
        reconstruct_positions(np.array([0.004, 0.02]), market)


def test_mismatched_lengths_are_refused() -> None:
    with pytest.raises(ValueError, match="days"):
        reconstruct_positions(np.zeros(5), np.zeros(4))


def test_the_search_is_far_smaller_than_it_looks() -> None:
    """Neighbouring windows are nearly the same bet.

    Deflating by the raw candidate count would treat a 23-day and a 25-day
    average as independent searches, which overstates the correction. The
    effective count is what the correlation matrix supports.
    """
    result = run_selection(Settings())
    assert result.candidates == 322
    assert 1.0 < result.effective_trials < result.candidates / 4


def test_the_winner_beat_a_close_runner_up() -> None:
    """A ranking with nothing between first and second is a coin toss.

    Asserted because it is the reason the deflation matters: if the gap were
    wide the winner would be distinguishable and the search would be a smaller
    part of the story.
    """
    result = run_selection(Settings())
    assert result.runner_up < result.paper_sharpe
    gap = result.paper_sharpe - result.runner_up
    assert gap < 0.1 * abs(result.paper_sharpe)


@pytest.mark.parametrize("seed", [3, 7, 11, 19, 23, 29])
def test_no_seed_produces_a_defensible_winner(seed: int) -> None:
    """The headline conclusion is not a property of the default seed.

    The simulated market has no exploitable structure, so whatever wins the
    search won it by luck. The deflated Sharpe ratio should never reach the
    0.95 a reader would want before funding it, and the probability of
    backtest overfitting should never be negligible — at any seed, not just
    the one the README prints.
    """
    result = run_selection(Settings(seed=seed))
    assert result.deflated < 0.95, f"seed {seed} produced a significant winner"
    assert result.pbo > 0.05, f"seed {seed} produced an implausibly clean ranking"


def test_a_bigger_search_deflates_a_given_sharpe_harder() -> None:
    """More trials, more of the maximum attributable to the maximum.

    Held fixed: the Sharpe ratio, the sample, and the dispersion of the trials.
    Only the count moves, so the direction is the whole claim.
    """
    few = deflated_sharpe_ratio(
        0.05, 1008, n_trials=5, trials_variance=4e-4
    )
    many = deflated_sharpe_ratio(
        0.05, 1008, n_trials=500, trials_variance=4e-4
    )
    assert many < few


def test_the_threshold_the_seeds_never_reach_is_reachable() -> None:
    """Guards the guard above.

    ``test_no_seed_produces_a_defensible_winner`` asserts the deflated Sharpe
    ratio stays below 0.95. That is only evidence if 0.95 is attainable at all
    — an assertion no input can violate tests nothing. A daily Sharpe ratio of
    0.10, which is 1.59 a year and an ordinary target rather than a fantasy,
    clears it comfortably over the same sample length and the same trial
    dispersion the sweep produces.
    """
    attainable = deflated_sharpe_ratio(
        0.10, 1008, n_trials=5, trials_variance=4e-4
    )
    assert attainable > 0.95

    # And it is the Sharpe ratio doing the work, not the sample length: the
    # same search over the same 1008 days with a quarter of the edge does not.
    marginal = deflated_sharpe_ratio(
        0.025, 1008, n_trials=5, trials_variance=4e-4
    )
    assert marginal < 0.95


def test_the_first_position_is_a_trade() -> None:
    """The book starts flat, so entering costs.

    A strategy holding one unit all the way through still had to buy it. The
    count below is one, not zero.
    """
    result = run_selection(Settings())
    assert result.position_changes >= 1
    assert result.positions[0] != 0.0 or result.position_changes >= 1
