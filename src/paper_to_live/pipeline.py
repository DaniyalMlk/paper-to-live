"""The four stages, run in order.

Each stage is a pure function of the settings and the stage before it, so
anything here can be run alone — a reader who only wants the execution cost
can call :func:`~paper_to_live.execution.run_execution` with a selection and
never touch the rest. This module exists for the common case of wanting all
four and the arithmetic that connects them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .execution import ExecutionResult, run_execution
from .funding import FundingResult, run_funding
from .risk import RiskResult, run_risk
from .selection import SelectionResult, run_selection
from .types import Settings


@dataclass(frozen=True, slots=True)
class Pipeline:
    """Every stage's result, and the erosion that connects them."""

    settings: Settings
    selection: SelectionResult
    execution: ExecutionResult
    risk: RiskResult
    funding: FundingResult

    @property
    def paper_sharpe(self) -> float:
        """What the backtest reported."""
        return self.selection.paper_sharpe_annual

    @property
    def surviving_sharpe(self) -> float:
        """What is left after execution and financing."""
        return self.funding.excess_sharpe_annual

    @property
    def execution_drag(self) -> float:
        """Sharpe ratio removed by trading the strategy."""
        return self.selection.paper_sharpe_annual - self.execution.net_sharpe_annual

    @property
    def funding_drag(self) -> float:
        """Sharpe ratio removed by paying for the capital."""
        return self.funding.net_sharpe_annual - self.funding.excess_sharpe_annual

    @property
    def fraction_surviving(self) -> float:
        """The surviving Sharpe ratio as a fraction of the paper one."""
        if self.paper_sharpe == 0.0:
            return 0.0
        return self.surviving_sharpe / self.paper_sharpe

    def as_dict(self) -> dict[str, Any]:
        """A flat mapping, for the ``--json`` output and for a test to pin."""
        return {
            "settings": {
                "days": self.settings.days,
                "seed": self.settings.seed,
                "trend": self.settings.trend,
                "notional": self.settings.notional,
                "daily_volume": self.settings.daily_volume,
                "impact_y": self.settings.impact_y,
                "confidence": self.settings.confidence,
                "valuation_date": self.settings.valuation_date.isoformat(),
            },
            "selection": {
                "candidates": self.selection.candidates,
                "effective_trials": self.selection.effective_trials,
                "winner_fast": self.selection.winner[0],
                "winner_slow": self.selection.winner[1],
                "paper_sharpe_annual": self.selection.paper_sharpe_annual,
                "deflated_sharpe": self.selection.deflated,
                "probability_of_overfitting": self.selection.pbo,
                "position_changes": self.selection.position_changes,
                "reconstruction_worst_error": (
                    self.selection.reconstruction.worst_error
                ),
                "reconstruction_ambiguous_days": (
                    self.selection.reconstruction.ambiguous_days
                ),
            },
            "execution": {
                "orders": len(self.execution.orders),
                "turnover_multiples_of_capital": self.execution.turnover,
                "annual_cost_bps": self.execution.annual_cost_bps,
                "largest_participation": self.execution.largest_participation,
                "peak_overstatement_bps": self.execution.peak_vs_average_bps,
                "net_sharpe_annual": self.execution.net_sharpe_annual,
            },
            "risk": {
                "confidence": self.risk.confidence,
                "value_at_risk_bps": self.risk.value_at_risk_bps,
                "expected_shortfall_bps": self.risk.expected_shortfall_bps,
                "tail_observations": self.risk.tail_observations,
                "max_drawdown": self.risk.max_drawdown,
                "longest_underwater_days": self.risk.longest_underwater_days,
            },
            "funding": {
                "horizon_years": self.funding.horizon_years,
                "zero_rate": self.funding.zero_rate,
                "worst_repricing_error": self.funding.worst_repricing_error,
                "hurdle_sharpe": self.funding.hurdle_sharpe,
                "excess_sharpe_annual": self.funding.excess_sharpe_annual,
            },
            "erosion": {
                "paper_sharpe_annual": self.paper_sharpe,
                "execution_drag": self.execution_drag,
                "funding_drag": self.funding_drag,
                "surviving_sharpe_annual": self.surviving_sharpe,
                "fraction_surviving": self.fraction_surviving,
            },
        }


def run(settings: Settings | None = None) -> Pipeline:
    """Run all four stages and return everything they produced."""
    settings = settings or Settings()
    selection = run_selection(settings)
    execution = run_execution(settings, selection)
    return Pipeline(
        settings=settings,
        selection=selection,
        execution=execution,
        risk=run_risk(settings, execution.net_returns),
        funding=run_funding(settings, execution.net_returns),
    )


__all__ = ["Pipeline", "run"]
