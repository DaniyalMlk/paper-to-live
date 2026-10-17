"""The command line: one command, one table.

Every option is a field of :class:`~paper_to_live.types.Settings`, so the
command line and the library agree by construction rather than by being kept
in step.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date

from . import __version__
from .pipeline import run
from .report import detail, erosion_table
from .types import Settings

#: The defaults the command line advertises, taken from an *instance*.
#: `Settings` has `slots=True`, so `Settings.days` is the slot descriptor and
#: not the default value — a mistake that type checks, renders plausibly in
#: `--help`, and only fails when the value is used. `test_defaults_match`
#: compares every option against this object so the two cannot drift either.
_DEFAULTS = Settings()


def _valuation_date(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError as error:  # pragma: no cover - argparse formats this
        raise argparse.ArgumentTypeError(
            f"expected a date as YYYY-MM-DD, got {text!r}"
        ) from error


def parser() -> argparse.ArgumentParser:
    """The argument parser, built once and shared with the help sweep."""
    command = argparse.ArgumentParser(
        prog="paper-to-live",
        description=(
            "Walk a backtested strategy from its paper Sharpe ratio to the "
            "number a desk would underwrite: what the search inflated, what "
            "execution took, what the book risks, and what the capital costs."
        ),
    )
    command.add_argument(
        "--version", action="version", version=f"paper-to-live {__version__}"
    )

    subcommands = command.add_subparsers(dest="command", metavar="COMMAND")

    run_command = subcommands.add_parser(
        "run",
        help="Run all four stages and print the erosion table.",
        description="Run all four stages and print the erosion table.",
    )
    run_command.add_argument(
        "--days",
        type=int,
        default=_DEFAULTS.days,
        help="Length of the backtest in trading days (default: %(default)s).",
    )
    run_command.add_argument(
        "--seed",
        type=int,
        default=_DEFAULTS.seed,
        help=(
            "Seed for the simulated market. The conclusion does not depend on "
            "it, which is the point of being able to change it "
            "(default: %(default)s)."
        ),
    )
    run_command.add_argument(
        "--trend",
        type=float,
        default=_DEFAULTS.trend,
        help=(
            "Strength of an exploitable drift in the market. Zero, the "
            "default, means there is nothing for the rules to find "
            "(default: %(default)s)."
        ),
    )
    run_command.add_argument(
        "--notional",
        type=float,
        default=_DEFAULTS.notional,
        help=(
            "Capital deployed, in currency. Sets the size of every parent "
            "order (default: %(default)s)."
        ),
    )
    run_command.add_argument(
        "--daily-volume",
        type=float,
        default=_DEFAULTS.daily_volume,
        help=(
            "Average daily volume of the traded instrument, in the same "
            "currency as the capital. Cost depends on the order as a fraction "
            "of this (default: %(default)s)."
        ),
    )
    run_command.add_argument(
        "--impact-y",
        type=float,
        default=_DEFAULTS.impact_y,
        help=(
            "Coefficient of the square-root impact law. Published estimates "
            "are of order one (default: %(default)s)."
        ),
    )
    run_command.add_argument(
        "--confidence",
        type=float,
        default=_DEFAULTS.confidence,
        help=(
            "Confidence level for value at risk and expected shortfall "
            "(default: %(default)s)."
        ),
    )
    run_command.add_argument(
        "--valuation-date",
        type=_valuation_date,
        default=_DEFAULTS.valuation_date,
        help=(
            "Reference date of the quoted screen the discount curve is built "
            "from, as YYYY-MM-DD (default: %(default)s)."
        ),
    )
    run_command.add_argument(
        "--json",
        action="store_true",
        help="Emit every figure as JSON instead of the table.",
    )
    run_command.add_argument(
        "--no-checks",
        action="store_true",
        help="Leave out the block of internal consistency checks.",
    )
    return command


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit status."""
    command = parser()
    arguments = command.parse_args(argv)
    if arguments.command is None:
        command.print_help()
        return 0

    settings = Settings(
        days=arguments.days,
        trend=arguments.trend,
        seed=arguments.seed,
        notional=arguments.notional,
        daily_volume=arguments.daily_volume,
        impact_y=arguments.impact_y,
        confidence=arguments.confidence,
        valuation_date=arguments.valuation_date,
    )

    try:
        pipeline = run(settings)
    except (ValueError, RuntimeError) as error:
        # A bad combination of settings is a user error, not a crash: the
        # message says which input was impossible rather than where.
        print(f"paper-to-live: {error}", file=sys.stderr)
        return 2

    if arguments.json:
        print(json.dumps(pipeline.as_dict(), indent=2, sort_keys=True))
        return 0

    print(erosion_table(pipeline))
    if not arguments.no_checks:
        print()
        print(detail(pipeline))
    return 0


__all__ = ["main", "parser"]
