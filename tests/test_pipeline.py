"""The four stages together, and the figures the README prints."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from paper_to_live.pipeline import Pipeline, run
from paper_to_live.report import detail, erosion_table
from paper_to_live.types import Settings

README = Path(__file__).resolve().parent.parent / "README.md"


@pytest.fixture(scope="module")
def default() -> Pipeline:
    return run()


def test_the_erosion_adds_up(default: Pipeline) -> None:
    """Paper, less execution, less financing, is what survives.

    An identity, so a term that was annualised twice or signed backwards
    shows here and not in any single stage's own tests, where it would still
    look like a number of about the right size.
    """
    assert (
        default.paper_sharpe - default.execution_drag - default.funding_drag
        == pytest.approx(default.surviving_sharpe, rel=1e-12)
    )


def test_each_stage_only_ever_takes_away(default: Pipeline) -> None:
    assert default.execution_drag > 0.0
    assert default.funding_drag > 0.0
    assert default.surviving_sharpe < default.paper_sharpe
    assert 0.0 < default.fraction_surviving < 1.0


@pytest.mark.parametrize("seed", [3, 7, 11, 19, 23])
def test_the_conclusion_does_not_depend_on_the_seed(seed: int) -> None:
    """The headline is a property of the exercise, not of one draw.

    Two claims, both across seeds. Execution and financing always take a
    real bite, and what survives is never something the deflated Sharpe
    ratio would support funding.
    """
    pipeline = run(Settings(seed=seed))
    assert pipeline.execution_drag > 0.0
    assert pipeline.funding_drag > 0.0
    assert pipeline.selection.deflated < 0.95


def test_every_published_figure_is_finite(default: Pipeline) -> None:
    """A NaN survives ``json.dumps`` and is not valid JSON.

    Walked rather than spot-checked, so a field added later is covered by
    this without anybody remembering to come back.
    """
    payload = default.as_dict()
    json.dumps(payload, allow_nan=False)
    for section, values in payload.items():
        for name, value in values.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                assert math.isfinite(value), f"{section}.{name}"


def test_the_pipeline_is_reproducible() -> None:
    """Same settings, same numbers. Nothing reads a clock or a global."""
    first = run(Settings(days=600)).as_dict()
    second = run(Settings(days=600)).as_dict()
    assert first == second


def test_a_deeper_market_leaves_more_of_the_strategy() -> None:
    """The pipeline responds to its inputs rather than reciting a story."""
    shallow = run(Settings(daily_volume=150e6))
    deep = run(Settings(daily_volume=1200e6))
    assert deep.fraction_surviving > shallow.fraction_surviving
    assert deep.execution_drag < shallow.execution_drag


def test_the_readme_prints_what_the_code_prints(default: Pipeline) -> None:
    """The README's table is the real output, not a remembered one.

    Pinned as a block rather than figure by figure: the README embeds the
    table verbatim, so the comparison is the whole thing and a single digit
    moving anywhere fails it. This is what stops the headline numbers drifting
    away from the code that produces them.
    """
    if not README.exists():  # pragma: no cover - the README is committed
        pytest.skip("README.md is not present")
    readme = README.read_text()
    table = erosion_table(default)
    assert table in readme, (
        "README.md does not contain the current erosion table. "
        "Regenerate it with: paper-to-live run"
    )
    assert detail(default) in readme
