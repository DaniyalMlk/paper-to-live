"""Stage one: the candidate set, and how much of the winner is the search.

A parameter sweep reports the Sharpe ratio of whichever rule came first. That
is the maximum of many draws, so it is biased upward even when no rule in the
grid has an edge, and the bias grows with the size of the search. This module
produces the candidate set and then says how much of the winner's performance
survives being told how hard it was looked for.

Nothing here decides whether the strategy is good. It produces the four
numbers a reader needs to decide: the paper Sharpe ratio, the effective number
of independent trials behind it, the probability that the winner's true Sharpe
ratio is above zero once the search is accounted for, and the probability that
the ranking itself is noise.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from holdout import (
    deflated_sharpe_ratio,
    effective_number_of_trials,
    estimate_sharpe,
    probability_of_backtest_overfitting,
    select_best,
    sharpe_ratio,
    sharpe_standard_error,
    trial_correlation,
)
from holdout.synthetic import crossover_sweep

from .types import FloatArray, Settings, annualised

#: Below this, a day's market return is too small to divide by: the position
#: that produced the strategy's return cannot be read back from it. Market
#: returns are daily log returns of order 1e-2, so this is five orders of
#: magnitude below anything the simulation produces.
_RECOVERABLE = 1e-12

#: How far a reconstructed position may sit from an integer before the
#: reconstruction is considered to have failed rather than merely rounded.
_SNAP_TOLERANCE = 1e-9


class ReconstructionFailed(RuntimeError):
    """The recovered positions do not reproduce the backtest they came from.

    Raised rather than warned. Every later stage prices the trades these
    positions imply, so a silent mismatch here would be a cost number computed
    for a strategy nobody ran.
    """


@dataclass(frozen=True, slots=True)
class Reconstruction:
    """Daily positions recovered from a strategy's return column.

    Attributes
    ----------
    positions
        One of -1, 0 or +1 for each day, the holding that produced the return.
    worst_error
        The largest absolute difference between ``positions * market`` and the
        strategy's own returns. Exact reconstruction gives zero.
    ambiguous_days
        Days whose market return was too small to divide by, where the previous
        position was carried forward. The carry-forward cannot be checked by
        ``worst_error`` — on such a day any position reproduces the return — so
        the count is published instead of being absorbed.
    """

    positions: FloatArray
    worst_error: float
    ambiguous_days: int


def reconstruct_positions(strategy: FloatArray, market: FloatArray) -> Reconstruction:
    """Recover the daily holdings behind a backtested return series.

    The sweep hands back what each rule earned, not what it held, and stage two
    needs the holdings: the cost of a strategy is set by how often and how far
    it moves, which the return series does not show. A rule that earns its
    Sharpe ratio from two position changes and one that earns the same from two
    hundred are the same column of numbers and are not the same strategy.

    Each strategy return is ``position * market return`` on the same day, so
    dividing recovers the position wherever the market moved at all. The result
    is checked against the series it came from and the check is an exception,
    not a flag.
    """
    if strategy.shape != market.shape:
        raise ValueError(
            f"strategy has {strategy.shape[0]} days and market has {market.shape[0]}"
        )

    positions = np.zeros_like(strategy)
    carried = 0.0
    ambiguous = 0
    for day in range(strategy.size):
        if abs(market[day]) > _RECOVERABLE:
            exact = strategy[day] / market[day]
            snapped = float(np.round(exact))
            if abs(exact - snapped) > _SNAP_TOLERANCE:
                raise ReconstructionFailed(
                    f"day {day}: implied position {exact!r} is not a whole holding"
                )
            carried = snapped
        else:
            ambiguous += 1
        positions[day] = carried

    residual = np.abs(positions * market - strategy)
    worst = float(np.max(residual)) if strategy.size else 0.0
    if worst > _SNAP_TOLERANCE:
        raise ReconstructionFailed(
            f"recovered positions miss the backtest by {worst!r} at worst"
        )
    return Reconstruction(
        positions=positions, worst_error=worst, ambiguous_days=ambiguous
    )


@dataclass(frozen=True, slots=True)
class SelectionResult:
    """The winner of a parameter search, and what the search cost its Sharpe.

    Attributes
    ----------
    candidates
        How many rules were tried.
    effective_trials
        Independent trials implied by the correlation between the candidates.
        Overlapping moving-average windows make neighbouring rules nearly the
        same bet, so this is far below ``candidates`` and deflating by the raw
        count would overstate the correction.
    winner
        The ``(fast, slow)`` window pair that came first.
    paper_sharpe, paper_sharpe_annual
        The winner's Sharpe ratio, per day and per year, as a backtest would
        report it.
    runner_up
        The second-best Sharpe ratio, per day. The gap to it is how much of the
        ranking rests on the winner being genuinely different.
    deflated
        Probability that the winner's true Sharpe ratio exceeds zero, given how
        many effectively independent rules were tried and how dispersed their
        results were. Not a Sharpe ratio: a probability, and the number to read
        against a threshold like 0.95.
    pbo
        Probability of backtest overfitting: across splits of the sample, how
        often the rule that wins in sample lands below median out of sample.
        Half is what pure noise gives.
    returns, market, positions
        The winner's daily returns, the market it traded, and the holdings
        recovered from them.
    reconstruction
        The audit of those holdings.
    """

    candidates: int
    effective_trials: float
    winner: tuple[int, int]
    paper_sharpe: float
    paper_sharpe_annual: float
    runner_up: float
    deflated: float
    pbo: float
    returns: FloatArray
    market: FloatArray
    positions: FloatArray
    reconstruction: Reconstruction

    @property
    def position_changes(self) -> int:
        """Days on which the holding moved, and so a trade had to be sent.

        The book starts flat, so establishing the first position counts. It is
        a real order and stage two charges for it; treating day one as already
        held would hand the strategy a free entry.
        """
        if self.positions.size == 0:
            return 0
        moves = np.diff(self.positions, prepend=0.0)
        return int(np.count_nonzero(moves))


def run_selection(settings: Settings) -> SelectionResult:
    """Search the grid, take the winner, and measure the search behind it."""
    sweep = crossover_sweep(
        settings.days,
        fast=settings.fast,
        slow=settings.slow,
        trend=settings.trend,
        seed=settings.seed,
    )
    table = np.asarray(sweep.table.values, dtype=np.float64)
    market = np.asarray(sweep.market, dtype=np.float64)
    periods, candidates = table.shape

    sharpes = [sharpe_ratio(table[:, j]) for j in range(candidates)]
    deviations = [sharpe_standard_error(s, periods) for s in sharpes]
    best = select_best(sharpes, deviations)
    winner_returns = np.asarray(table[:, best.index], dtype=np.float64)

    # Deflation needs the shape of the winner's own return distribution — a
    # Sharpe ratio estimated on skewed, fat-tailed returns is less certain than
    # the same number on normal ones — and the dispersion of the trials it beat.
    moments = estimate_sharpe(winner_returns)
    effective = effective_number_of_trials(
        trial_correlation(table), method="eigenvalue"
    )
    deflated = deflated_sharpe_ratio(
        best.estimate,
        periods,
        n_trials=max(1, round(effective)),
        trials_variance=float(np.var(sharpes, ddof=1)),
        trials_mean=float(np.mean(sharpes)),
        skewness=moments.skewness,
        kurtosis=moments.kurtosis,
    )
    overfitting = probability_of_backtest_overfitting(table, n_blocks=16)
    reconstruction = reconstruct_positions(winner_returns, market)

    return SelectionResult(
        candidates=candidates,
        effective_trials=float(effective),
        winner=sweep.parameters[best.index],
        paper_sharpe=best.estimate,
        paper_sharpe_annual=annualised(best.estimate),
        runner_up=best.threshold,
        deflated=deflated,
        pbo=float(overfitting.pbo),
        returns=winner_returns,
        market=market,
        positions=reconstruction.positions,
        reconstruction=reconstruction,
    )
