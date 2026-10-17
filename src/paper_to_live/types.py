"""Shared aliases and the settings every stage reads.

Each stage is a pure function of :class:`Settings` and the stage before it, so
the whole pipeline is reproducible from one small dataclass and nothing is
carried between stages in a mutable buffer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import TypeAlias

import numpy as np
import numpy.typing as npt

FloatArray: TypeAlias = npt.NDArray[np.float64]

#: Trading days in a year. Everything in this package is stated per day and
#: annualised at the boundary, so this appears here once rather than inline.
PERIODS_PER_YEAR = 252.0


@dataclass(frozen=True, slots=True)
class Settings:
    """Everything the pipeline needs, with defaults that are stated, not hidden.

    Parameters
    ----------
    days
        Length of the backtest in trading days, after the warm-up the longest
        moving average needs is dropped.
    fast, slow
        The moving-average grid searched. Their product, minus the pairs where
        the fast window is not shorter than the slow one, is the size of the
        search.
    trend
        Strength of an exploitable drift in the simulated market. Zero means
        there is nothing to find, which is the point of the default: the
        winner's performance is then entirely selection.
    seed
        Seed for the market simulation. The conclusion should not depend on it,
        and a test asserts that it does not.
    notional
        Capital deployed, in currency. Sets the size of every parent order.
    daily_volume
        Average daily volume of the traded instrument, in the same currency.
        Cost depends on the order as a fraction of this, so the pair of numbers
        matters and neither alone does.
    impact_y
        The coefficient of the square-root impact law. Published estimates are
        of order one.
    confidence
        Confidence level for value at risk and expected shortfall.
    valuation_date
        Reference date of the quoted screen the discount curve is built from.
    """

    days: int = 1008
    fast: tuple[int, ...] = (3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29)
    slow: tuple[int, ...] = (
        40, 50, 60, 70, 80, 90, 100, 110, 120, 130,
        140, 150, 160, 170, 180, 190, 200, 210, 220, 230, 240, 250, 260,
    )  # fmt: skip
    trend: float = 0.0
    seed: int = 11
    notional: float = 50_000_000.0
    daily_volume: float = 300_000_000.0
    impact_y: float = 0.8
    confidence: float = 0.99
    valuation_date: date = date(2021, 1, 5)

    @property
    def years(self) -> float:
        """Length of the backtest in years."""
        return self.days / PERIODS_PER_YEAR


def annualised(per_period: float) -> float:
    """A per-period Sharpe ratio stated per year."""
    return per_period * math.sqrt(PERIODS_PER_YEAR)


def to_bps(fraction: float) -> float:
    """A fraction of notional in basis points."""
    return fraction * 10_000.0
