"""The one output: where the paper Sharpe ratio went.

Plain text with no dependency on a terminal, so the same bytes appear in a
pipe, in CI and in the README. The README's copy is reproduced by a test, so
the figures in it cannot quietly drift away from the figures the code emits.
"""

from __future__ import annotations

from .pipeline import Pipeline

_WIDTH = 72


def _rule(character: str = "-") -> str:
    return character * _WIDTH


def _row(label: str, value: str, note: str = "") -> str:
    return f"  {label:<34}{value:>12}  {note}".rstrip()


def erosion_table(pipeline: Pipeline) -> str:
    """The headline: a backtest's Sharpe ratio and what is left of it."""
    selection = pipeline.selection
    execution = pipeline.execution
    risk = pipeline.risk
    funding = pipeline.funding

    lines = [
        _rule("="),
        "  FROM PAPER TO LIVE",
        _rule("="),
        "",
        f"  A search over {selection.candidates} moving-average rules"
        f" ({selection.effective_trials:.0f} effectively independent),",
        f"  {pipeline.settings.days} trading days, "
        f"{pipeline.settings.notional / 1e6:.0f}m of capital against "
        f"{pipeline.settings.daily_volume / 1e6:.0f}m of daily volume.",
        "",
        _rule(),
        "  WHERE THE SHARPE RATIO WENT",
        _rule(),
        _row(
            "Paper (what the backtest said)",
            f"{pipeline.paper_sharpe:+.2f}",
            f"rule {selection.winner[0]}/{selection.winner[1]}",
        ),
        _row(
            "less execution",
            f"{-pipeline.execution_drag:+.2f}",
            f"{execution.annual_cost_bps:.0f} bps a year",
        ),
        _row(
            "less financing",
            f"{-pipeline.funding_drag:+.2f}",
            f"{funding.zero_rate * 100:.2f}% at "
            f"{funding.horizon_years:.0f}y",
        ),
        _rule(),
        _row(
            "Surviving",
            f"{pipeline.surviving_sharpe:+.2f}",
            f"{pipeline.fraction_surviving * 100:.0f}% of the paper figure",
        ),
        "",
        _rule(),
        "  AND WHETHER ANY OF IT IS REAL",
        _rule(),
        _row(
            "P(true Sharpe > 0) after search",
            f"{selection.deflated:.2f}",
            "wanted: > 0.95",
        ),
        _row(
            "P(the ranking is overfit)",
            f"{selection.pbo:.2f}",
            "0.50 is pure noise",
        ),
        "",
        _rule(),
        "  WHAT IT WOULD HAVE TAKEN TO HOLD",
        _rule(),
        _row(
            f"Expected shortfall ({risk.confidence:.0%}, 1 day)",
            f"{risk.expected_shortfall_bps:.0f} bps",
            f"from {risk.tail_observations} tail days",
        ),
        _row(
            "Deepest drawdown",
            f"{risk.max_drawdown * 100:.1f}%",
            f"{risk.longest_underwater_days} days under water",
        ),
        _row(
            "Turnover",
            f"{execution.turnover:.0f}x",
            f"{len(execution.orders)} orders, "
            f"largest {execution.largest_participation:.0%} of a day",
        ),
        "",
        _rule("="),
    ]
    return "\n".join(lines)


def detail(pipeline: Pipeline) -> str:
    """The checks a reader should be able to see rather than take on trust."""
    selection = pipeline.selection
    execution = pipeline.execution
    funding = pipeline.funding
    lines = [
        "  CHECKS",
        _rule(),
        _row(
            "Positions reproduce the backtest",
            f"{selection.reconstruction.worst_error:.1e}",
            f"{selection.reconstruction.ambiguous_days} ambiguous days",
        ),
        _row(
            "Curve reprices its own quotes",
            f"{funding.worst_repricing_error:.1e}",
            "4 instruments",
        ),
        _row(
            "Peak impact would have overstated",
            f"{execution.peak_vs_average_bps:.0f} bps",
            "published coefficients are peaks",
        ),
    ]
    schedule = execution.representative
    if schedule is not None:
        lines.append(
            _row(
                "Largest order, first half of day",
                f"{schedule.front_loading:.0%}",
                f"{schedule.slices} slices, "
                f"{schedule.expected_cost_bps:.1f} bps",
            )
        )
    return "\n".join(lines)


__all__ = ["detail", "erosion_table"]
