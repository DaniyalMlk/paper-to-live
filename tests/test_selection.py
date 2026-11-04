"""Stage one: the candidate set and the deflation of its winner."""

from __future__ import annotations

import numpy as np
import pytest
from holdout import ValidationError, deflated_sharpe_ratio

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


class TestChoosingTheGrid:
    """``Settings.fast`` and ``Settings.slow``, actually chosen.

    Both are documented knobs that no call site in this repository had ever
    set. They looked exercised to a probe keyed on parameter name, because
    ``run_selection`` forwards them as ``crossover_sweep(fast=settings.fast,
    slow=settings.slow)`` — which passes the defaults onward rather than
    choosing anything.
    """

    def test_the_default_grid_is_the_full_product_of_the_two_tuples(self) -> None:
        # Every fast window is shorter than every slow one by construction:
        # max(fast) is 29 and min(slow) is 40. So nothing is filtered, and the
        # candidate count is the plain product -- which is what makes the
        # filtered cases below a genuine change rather than a coincidence.
        settings = Settings()
        assert max(settings.fast) < min(settings.slow)
        assert len(settings.fast) * len(settings.slow) == 322
        assert run_selection(settings).candidates == 322

    def test_choosing_a_smaller_grid_changes_the_search_and_the_winner(self) -> None:
        default = run_selection(Settings())
        small = run_selection(Settings(fast=(5, 10, 15), slow=(40, 60), days=300))
        assert small.candidates == 6
        assert default.candidates == 322
        # The option is chosen with a value that moves the result, not merely
        # accepted: the winner, the effective trial count and the deflated
        # Sharpe all differ.
        assert small.winner != default.winner
        assert small.effective_trials < default.effective_trials
        assert small.deflated != default.deflated

    def test_the_grid_filter_is_visible_from_here(self) -> None:
        # Interleaved tuples: 3 x 3 offered, and the three pairs where the fast
        # window is not strictly shorter than the slow one are dropped. The
        # default grid cannot show this, because it filters nothing.
        fast, slow = (3, 5, 7), (5, 7, 9)
        kept = [(f, s) for f in fast for s in slow if f < s]
        assert len(fast) * len(slow) == 9
        assert len(kept) == 6
        assert run_selection(Settings(fast=fast, slow=slow, days=300)).candidates == 6

    def test_a_shorter_slow_window_permits_a_shorter_backtest(self) -> None:
        # The coupling that was never exercised: the sample length floor is
        # 2 * max(slow), so choosing slow is what makes days choosable. At the
        # default slow the floor is 520 and 300 days is refused; narrow slow to
        # (40, 60) and the same 300 days is ample.
        assert 2 * max(Settings().slow) == 520
        with pytest.raises(ValidationError, match="n_days must be at least 520"):
            run_selection(Settings(days=300))
        narrowed = Settings(fast=(5, 10), slow=(40, 60), days=300)
        assert 2 * max(narrowed.slow) == 120
        assert run_selection(narrowed).candidates == 4

    def test_a_degenerate_grid_is_refused_by_the_library(self) -> None:
        # The grids reachable from this configuration that have no backtestable
        # pair: an empty fast or slow, and a grid where no fast window is
        # strictly shorter than a slow one. Each is refused by holdout rather
        # than failing inside numpy -- the defect this exposure found upstream,
        # fixed there and pinned there, in holdout #48 / #49.
        #
        # What is asserted here is only that the refusal arrives and is a
        # library error, not its wording. The published holdout and the fixed
        # one both carry version 0.1.0, so which of them a resolve picks up is
        # not something this repository can state, and asserting the new
        # messages here made this suite fail against the released wheel while
        # passing against main. The messages belong to the library's own tests.
        degenerate = (((), (40,)), ((5,), ()), ((40,), (40,)), ((50, 60), (40, 50)))
        for fast, slow in degenerate:
            with pytest.raises(ValueError):
                run_selection(Settings(fast=fast, slow=slow, days=600))
