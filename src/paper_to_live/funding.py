"""Stage four: what the capital costs.

A Sharpe ratio is defined on returns in excess of a risk-free rate, and a
backtest that subtracts nothing has quietly set that rate to zero. In a decade
when cash paid nothing that was close enough to true to be ignored. It is not
a small correction at three per cent: a strategy earning four per cent a year
with a six per cent volatility has a Sharpe ratio of 0.67 against zero and
0.17 against the curve, and only one of those two numbers is the one a desk
would be judged on.

So this stage does not invent a financing spread or a leverage assumption. It
builds a discount curve from a quoted screen, reads the zero rate over the
horizon the backtest actually covers, and restates the Sharpe ratio in excess
of it. The screen is an input, not a constant, because the answer depends
entirely on when the strategy was run.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
from tenor import (
    Basis,
    Bootstrapped,
    Compounding,
    Deposit,
    Frequency,
    Instrument,
    Swap,
    bootstrap,
)

from .types import PERIODS_PER_YEAR, FloatArray, Settings, annualised

#: A plausible screen: one money-market deposit and three par swaps. Rates are
#: the input that decides this stage's answer, so they are stated here in one
#: place rather than spread through the code, and `screen_for` takes a
#: replacement.
_QUOTES: tuple[tuple[str, int, float], ...] = (
    ("deposit", 181, 0.0210),
    ("swap", 730, 0.0255),
    ("swap", 1826, 0.0290),
    ("swap", 3653, 0.0310),
)


def screen_for(reference: date) -> tuple[Instrument, ...]:
    """The quoted instruments the discount curve is built from.

    Tenors are offsets from the reference date rather than fixed dates, so the
    screen stays well formed whatever valuation date it is asked for.
    """
    instruments: list[Instrument] = []
    for kind, days, rate in _QUOTES:
        maturity = reference + timedelta(days=days)
        if kind == "deposit":
            instruments.append(Deposit(reference, maturity, rate, Basis.ACT_360))
        else:
            instruments.append(
                Swap(
                    reference,
                    maturity,
                    rate,
                    Frequency.SEMI_ANNUAL,
                    Basis.THIRTY_360_BOND,
                )
            )
    return tuple(instruments)


@dataclass(frozen=True, slots=True)
class FundingResult:
    """The curve the capital is funded on, and what it does to the Sharpe ratio.

    Attributes
    ----------
    horizon_years
        Length of the backtest, which is the tenor the financing rate is read
        at. A four-year holding is funded at the four-year point and not at
        the overnight rate.
    zero_rate
        Continuously compounded zero rate at that tenor, from the bootstrapped
        curve.
    discount_factor
        Present value of one unit paid at the horizon. Reported because it is
        the curve's own output and lets a reader check the rate by hand.
    worst_repricing_error
        The largest error with which the bootstrapped curve reprices the
        instruments it was built from. A curve that does not reprice its own
        inputs is not a curve, so this is a gate rather than a diagnostic.
    net_sharpe_annual
        Annualised Sharpe ratio before financing: the number stage two left.
    excess_sharpe_annual
        The same ratio with the financing rate subtracted from every return.
        This is the number the strategy is actually judged on.
    hurdle_sharpe
        The financing rate divided by the strategy's annualised volatility:
        the Sharpe ratio a strategy needs just to break even against cash.
    """

    horizon_years: float
    zero_rate: float
    discount_factor: float
    worst_repricing_error: float
    net_sharpe_annual: float
    excess_sharpe_annual: float
    hurdle_sharpe: float


def build_curve(settings: Settings) -> Bootstrapped:
    """Bootstrap a discount curve from the quoted screen."""
    return bootstrap(
        settings.valuation_date,
        screen_for(settings.valuation_date),
        basis=Basis.ACT_365F,
    )


def run_funding(settings: Settings, net_returns: FloatArray) -> FundingResult:
    """Restate the net Sharpe ratio in excess of the cost of the capital."""
    if net_returns.size < 2:
        raise ValueError("a Sharpe ratio needs at least two observations")

    curve = build_curve(settings)
    horizon = net_returns.size / PERIODS_PER_YEAR
    zero = curve.curve.zero_rate_at(horizon, Compounding.CONTINUOUS)

    # The daily financing charge. The continuously compounded rate divides
    # evenly across the year, which is what makes continuous the convenient
    # convention to read the curve in: no compounding frequency has to be
    # matched to the return series' own.
    daily = zero / PERIODS_PER_YEAR

    deviation = float(np.std(net_returns, ddof=1))
    net = float(np.mean(net_returns)) / deviation if deviation else 0.0
    excess = (float(np.mean(net_returns)) - daily) / deviation if deviation else 0.0
    volatility = annualised(deviation)

    return FundingResult(
        horizon_years=horizon,
        zero_rate=zero,
        discount_factor=curve.curve.discount_at(horizon),
        worst_repricing_error=float(curve.worst_error),
        net_sharpe_annual=annualised(net),
        excess_sharpe_annual=annualised(excess),
        hurdle_sharpe=zero / volatility if volatility else float("inf"),
    )


__all__ = ["FundingResult", "build_curve", "run_funding", "screen_for"]
