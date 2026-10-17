"""Stage two: what it costs to put the strategy on.

A backtest trades at the close, in unlimited size, for nothing. A desk trades
a position into a market that moves away from it as it goes, and the move is
not a fee that can be negotiated — it is the price of demanding liquidity
faster than it arrives.

This stage turns the holdings recovered in stage one into parent orders,
prices them under a stated impact law, and hands back the return series net of
what that costs. Every input that sets the answer — the capital deployed, the
volume available, the coefficient of the impact law — is named in
:class:`~paper_to_live.types.Settings` rather than buried here, because the
cost is a function of the order as a fraction of daily volume and no single
one of those numbers means anything alone.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from slippage import ExecutionProblem, LinearImpact, SquareRootLaw, optimal_trajectory

from .selection import SelectionResult
from .types import FloatArray, Settings, annualised, to_bps

#: Intervals the representative parent order is sliced into when its optimal
#: trajectory is drawn. One a quarter-hour over a six-and-a-half hour session.
_SLICES = 26

#: Risk aversion for the representative trajectory, in inverse currency: one
#: unit of expected cost traded against a million squared units of variance.
#: At the sizes here that puts the variance penalty and the impact cost within
#: a factor of two of each other, which is the regime where the shape of the
#: schedule is a decision rather than a rounding error. An order of magnitude
#: lower and the optimal schedule is indistinguishable from trading evenly.
_RISK_AVERSION = 1e-6


@dataclass(frozen=True, slots=True)
class Order:
    """A parent order the strategy had to send, and what it cost.

    Attributes
    ----------
    day
        Index into the backtest.
    quantity
        Currency traded, unsigned. A reversal from long to short trades twice
        the book.
    participation
        The order as a fraction of a day's volume.
    cost_fraction
        Average impact paid, as a fraction of the price traded at.
    cost_currency
        ``quantity * cost_fraction``.
    """

    day: int
    quantity: float
    participation: float
    cost_fraction: float
    cost_currency: float


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """The strategy as it would have been traded, not as it was backtested.

    Attributes
    ----------
    orders
        Every parent order, in order.
    net_returns
        Daily returns after the day's execution cost, as a fraction of capital.
    turnover
        Total currency traded over the backtest, as a multiple of capital.
    total_cost_bps
        Everything execution took, in basis points of capital.
    annual_cost_bps
        The same, per year.
    gross_sharpe_annual, net_sharpe_annual
        Annualised Sharpe ratio before and after cost.
    largest_participation
        The biggest single order as a fraction of a day's volume. The impact
        law is an extrapolation above roughly a third of volume, so a reader
        should see this number rather than take the cost on trust.
    peak_vs_average_bps
        What quoting the peak impact instead of the average paid would have
        added. Published impact estimates are peaks; charging a schedule the
        peak overstates it, and the size of that mistake belongs in the open.
    representative
        The optimal intraday trajectory for the largest order, as a sanity
        check that the day's trading is a schedule and not a single print.
    """

    orders: tuple[Order, ...]
    net_returns: FloatArray
    turnover: float
    total_cost_bps: float
    annual_cost_bps: float
    gross_sharpe_annual: float
    net_sharpe_annual: float
    largest_participation: float
    peak_vs_average_bps: float
    representative: RepresentativeSchedule | None


@dataclass(frozen=True, slots=True)
class RepresentativeSchedule:
    """An Almgren-Chriss trajectory for the backtest's largest order.

    Attributes
    ----------
    quantity
        Currency the schedule executes.
    slices
        Intervals it is cut into.
    front_loading
        Fraction of the order done in the first half of the session. A
        risk-neutral trader spreads evenly and this is one half; risk aversion
        pulls it forward, and the number says how far.
    expected_cost_bps
        Impact cost of the trajectory, in basis points of the order.
    eta
        The linear temporary-impact coefficient the trajectory was solved
        with, fitted to the square-root law this stage prices with so that the
        two are describing the same market.
    """

    quantity: float
    slices: int
    front_loading: float
    expected_cost_bps: float
    eta: float


def _fit_linear_eta(
    law: SquareRootLaw, quantity: float, settings: Settings, volatility: float
) -> float:
    """A linear temporary-impact coefficient that agrees with the square-root law.

    Almgren-Chriss is solved in closed form only for linear impact, while the
    cost actually charged in this stage comes from the square-root law, which
    is the better-evidenced of the two. Solving the trajectory under one law
    and charging under another would be two different markets.

    So ``eta`` is set by matching at the order being scheduled: the linear
    model is required to charge what the square-root law charges for *this*
    order at *this* rate. The trajectory is then a shape, valid near that
    size, rather than a claim that impact is linear everywhere.
    """
    if quantity <= 0.0:
        return 0.0
    # Under linear impact, trading ``Q`` at a constant rate over one day costs
    # ``eta * Q**2``: each slice pays ``eta`` times the rate, and the rate over
    # a whole day is ``Q`` itself. The square-root law charges ``Q`` times its
    # cost fraction. Equating the two gives the coefficient below.
    fraction = law.expected_cost(quantity, settings.daily_volume, volatility)
    return fraction / quantity


def _representative_schedule(
    law: SquareRootLaw, quantity: float, settings: Settings, volatility: float
) -> RepresentativeSchedule | None:
    """Draw the intraday trajectory for the largest order of the backtest."""
    if quantity <= 0.0:
        return None
    eta = _fit_linear_eta(law, quantity, settings, volatility)
    problem = ExecutionProblem(
        quantity=quantity,
        horizon=1.0,
        periods=_SLICES,
        volatility=volatility,
        # Permanent impact is zero here, and that is a statement rather than a
        # default. The square-root law this stage charges with is an estimate
        # of what a metaorder pays all in; it does not separate the part of the
        # move that stays behind. Adding a permanent term on top of it would
        # charge that part twice. With gamma at zero the risk-neutral
        # trajectory costs exactly what the square-root law charges, which is
        # the identity `test_the_risk_neutral_trajectory_agrees_with_the_law`
        # checks rather than assumes.
        impact=LinearImpact(gamma=0.0, eta=eta),
    )
    trajectory = optimal_trajectory(problem, risk_aversion=_RISK_AVERSION)
    trades = np.asarray(trajectory.trades, dtype=np.float64)
    half = trades.size // 2
    front = float(np.sum(trades[:half]) / quantity) if quantity else 0.0
    return RepresentativeSchedule(
        quantity=quantity,
        slices=_SLICES,
        front_loading=front,
        expected_cost_bps=to_bps(trajectory.expected_cost / quantity),
        eta=eta,
    )


def run_execution(
    settings: Settings, selection: SelectionResult
) -> ExecutionResult:
    """Price the strategy's trades and net them out of its returns."""
    positions = selection.positions
    market = selection.market
    gross = selection.returns

    # Daily volatility in the units the impact law wants: a fraction of price,
    # taken from the market the strategy traded rather than assumed.
    volatility = float(np.std(market, ddof=1))
    law = SquareRootLaw(y=settings.impact_y, delta=0.5)

    # The book starts flat and ends flat. Entering the first position is a real
    # order and so is unwinding the last one; charging for neither would hand
    # the strategy a free round trip.
    changes = np.diff(positions, prepend=0.0, append=0.0)
    traded = np.abs(changes) * settings.notional

    orders: list[Order] = []
    drag = np.zeros_like(gross)
    peak_total = 0.0
    for day, quantity in enumerate(traded):
        if quantity <= 0.0:
            continue
        fraction = law.expected_cost(quantity, settings.daily_volume, volatility)
        currency = quantity * fraction
        peak = law.peak_impact(quantity, settings.daily_volume, volatility)
        peak_total += quantity * peak
        orders.append(
            Order(
                day=day,
                quantity=float(quantity),
                participation=float(quantity / settings.daily_volume),
                cost_fraction=float(fraction),
                cost_currency=float(currency),
            )
        )
        # The unwind on the day after the last return has nowhere to land in
        # the series, so it is charged against the final day.
        drag[min(day, drag.size - 1)] += currency / settings.notional

    net = gross - drag
    total_cost = float(np.sum(drag))
    paid = sum(order.cost_currency for order in orders)

    largest = max((order.quantity for order in orders), default=0.0)
    return ExecutionResult(
        orders=tuple(orders),
        net_returns=net,
        turnover=float(np.sum(traded) / settings.notional),
        total_cost_bps=to_bps(total_cost),
        annual_cost_bps=to_bps(total_cost / settings.years),
        gross_sharpe_annual=annualised(_sharpe(gross)),
        net_sharpe_annual=annualised(_sharpe(net)),
        largest_participation=float(largest / settings.daily_volume),
        peak_vs_average_bps=to_bps((peak_total - paid) / settings.notional),
        representative=_representative_schedule(
            law, float(largest), settings, volatility
        ),
    )


def _sharpe(returns: FloatArray) -> float:
    """Per-period Sharpe ratio, in excess of nothing.

    Stage four is where a financing rate enters. Subtracting one here as well
    would charge for the capital twice.
    """
    deviation = float(np.std(returns, ddof=1))
    if deviation == 0.0:
        return 0.0
    return float(np.mean(returns)) / deviation


def annual_drag_on_sharpe(result: ExecutionResult) -> float:
    """How much annualised Sharpe ratio execution removed."""
    return result.gross_sharpe_annual - result.net_sharpe_annual


__all__ = [
    "ExecutionResult",
    "Order",
    "RepresentativeSchedule",
    "annual_drag_on_sharpe",
    "run_execution",
]
