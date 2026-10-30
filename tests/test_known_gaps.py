"""The README's known gaps, and whether each one is still a gap.

A list of omissions is read as current whether or not it is, so the failure
mode is not an incomplete list but a stale one: two of a sibling repository's
gap lines turned out to describe things that had been built months earlier. So
each line here is paired with a predicate, and the test fails four ways — a
line with no predicate, a predicate with no line, the list quietly shrinking,
and a predicate that no longer holds because the thing it says is missing has
arrived.

Most predicates ask whether anything in the package is *named* for the missing
cost. That is weaker than asking whether the cost is charged, and weaker in the
safe direction: a name can appear without the arithmetic behind it, at which
point the line comes out and is replaced by something sharper. What cannot
happen is the arithmetic arriving while the line stays. Where a sharper check
is available it is used instead — the holding being one of three values, and
the financing charge not depending on what was held, are both read off the
pipeline itself.
"""

from __future__ import annotations

import ast
import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import paper_to_live
from paper_to_live import funding
from paper_to_live.pipeline import run
from paper_to_live.types import Settings

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
PACKAGE = ROOT / "src" / "paper_to_live"


def _names() -> frozenset[str]:
    """Every name the package binds: imports, definitions, fields, arguments.

    Read off the syntax rather than by importing and introspecting, so that a
    field on a dataclass, a parameter on a function and a module-level constant
    are all found the same way, and a name that exists only inside a function
    body is found too.
    """
    found: set[str] = set()
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                found.add(node.name)
            elif isinstance(node, ast.arg):
                found.add(node.arg)
            elif isinstance(node, ast.Name):
                found.add(node.id)
            elif isinstance(node, ast.Attribute):
                found.add(node.attr)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                found.add(node.target.id)
            elif isinstance(node, ast.keyword) and node.arg:
                found.add(node.arg)
    found.update(name for name in dir(paper_to_live) if not name.startswith("_"))
    return frozenset(found)


NAMES = _names()


def _nothing_named(pattern: str) -> bool:
    expression = re.compile(pattern, re.IGNORECASE)
    return not any(expression.search(name) for name in NAMES)


@dataclass(frozen=True, slots=True)
class Gap:
    #: The bolded lead of the README bullet, exactly as written.
    heading: str
    #: True while the gap is still a gap.
    still_open: Callable[[], bool]


def _holdings_are_three_valued() -> bool:
    pipeline = run(Settings(days=600))
    return set(np.unique(pipeline.selection.positions)) <= {-1.0, 0.0, 1.0}


def _financing_ignores_the_holding() -> bool:
    """The charge is struck on the capital, not on the position.

    Read off the signature: `run_funding` is handed the return series and
    nothing else, so there is no way for it to know what was held on any
    given day, let alone to earn the rate on a short's proceeds.
    """
    parameters = set(inspect.signature(funding.run_funding).parameters)
    return parameters == {"settings", "net_returns"}


def _the_curve_is_one_screen_at_one_horizon() -> bool:
    result = run(Settings(days=600)).funding
    return isinstance(result.zero_rate, float) and len(funding._QUOTES) == 4


GAPS: tuple[Gap, ...] = (
    Gap(
        "One instrument.",
        lambda: _nothing_named(r"universe|constituent|cross_section"),
    ),
    Gap("The holding is one of three values.", _holdings_are_three_valued),
    Gap(
        "No borrow cost, and no borrow at all.",
        lambda: _nothing_named(r"borrow|locate"),
    ),
    Gap(
        "Financing is charged on the capital, every day.",
        _financing_ignores_the_holding,
    ),
    Gap(
        "One screen, read at one horizon.",
        _the_curve_is_one_screen_at_one_horizon,
    ),
    Gap("No capacity.", lambda: _nothing_named(r"capacity|decay|self_impact")),
    Gap("No tax.", lambda: _nothing_named(r"\btax")),
    Gap(
        "No dividends and no corporate actions.",
        lambda: _nothing_named(r"dividend|corporate_action|stock_split"),
    ),
    Gap(
        "Execution is a cost law, not a market.",
        lambda: _nothing_named(r"latency|queue|venue|order_book|spread_crossed"),
    ),
    Gap(
        "One currency.",
        # Not simply "currency": `cost_currency` is an amount in money and
        # `currency` names that idea throughout. What would have to appear for
        # this gap to be closed is a second one to convert into.
        lambda: _nothing_named(
            r"base_currency|quote_currency|exchange_rate|fx_rate|currency_pair"
        ),
    ),
    Gap("No regime.", lambda: _nothing_named(r"regime_switch|stress_scenario|crisis")),
)


def _readme_headings() -> list[str]:
    text = README.read_text(encoding="utf8")
    section = re.search(r"\n## Known gaps\n(.*?)(?=\n## )", text, re.DOTALL)
    assert section is not None, "the README has no known-gaps section"
    return re.findall(r"^- \*\*(.+?)\*\*", section.group(1), re.MULTILINE)


class TestTheKnownGapsList:
    def test_the_readme_lists_exactly_these_gaps_in_this_order(self) -> None:
        assert _readme_headings() == [gap.heading for gap in GAPS]

    def test_the_list_has_not_quietly_shrunk(self) -> None:
        assert len(GAPS) == 11

    def test_every_gap_is_still_a_gap(self) -> None:
        closed = [gap.heading for gap in GAPS if not gap.still_open()]
        assert closed == [], (
            "these gaps look closed; take the lines out of the README and the "
            f"entries out of this table: {closed}"
        )

    def test_the_inventory_the_predicates_read_is_not_empty(self) -> None:
        # A predicate of the form "nothing is named X" passes trivially over an
        # empty inventory, so the inventory is asserted: enough names, and four
        # that are certainly among them.
        assert len(NAMES) > 300
        for certain in ("run_funding", "participation", "impact_y", "positions"):
            assert certain in NAMES
        assert not _nothing_named(r"participation")

    def test_every_gap_says_which_way_it_moves_the_answer(self) -> None:
        # The reason the list exists: each omission flatters the surviving
        # Sharpe ratio, and a line that does not say so is not doing its job.
        text = README.read_text(encoding="utf8")
        section = re.search(r"\n## Known gaps\n(.*?)(?=\n## )", text, re.DOTALL)
        assert section is not None
        bullets = re.split(r"^- \*\*", section.group(1), flags=re.MULTILINE)[1:]
        assert len(bullets) == len(GAPS)
        for bullet in bullets:
            assert len(bullet.split()) > 25, bullet[:60]


class TestTheSuiteSizeTheReadmeStates:
    """A count in prose with nothing recomputing it stops being true quietly.

    This README said 100 tests, and there were 118 before this file was added.
    Nothing had been wrong since the figure was written; it had simply been
    written once. The bound is loose because a suite cannot count itself from
    inside without recursing, so the count is taken in a subprocess and the
    claim is that the figure is in the right neighbourhood rather than exact.
    """

    @staticmethod
    def _stated() -> int:
        text = README.read_text(encoding="utf8")
        match = re.search(r"(\d[\d,]*) tests on Python", text)
        assert match is not None, "the README no longer states a suite size"
        return int(match.group(1).replace(",", ""))

    def test_the_readme_states_a_size(self) -> None:
        assert self._stated() > 0

    def test_the_stated_size_is_within_a_quarter_of_the_real_one(self) -> None:
        import subprocess
        import sys

        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", "-o", "addopts="],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        collected = re.search(r"(\d+) tests? collected", completed.stdout)
        assert collected is not None, completed.stdout[-500:]
        actual = int(collected.group(1))
        stated = self._stated()
        assert actual > 50
        assert 0.75 * actual <= stated <= 1.25 * actual, (stated, actual)
