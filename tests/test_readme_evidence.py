"""The figures on the front page are the figures the pipeline produces.

This repository's whole argument is a table of numbers, and a table of numbers
in a document is worth exactly as much as the guarantee that it still matches.
A figure copied in once stops being true quietly: a library underneath changes,
the suite stays green because nothing in it reads the document, and the front
page goes on claiming a result the pipeline no longer gets.

That risk is higher here than in the libraries. This repository depends on four
of them and CI builds each from its default branch at job time, so the numbers
can move without a single commit landing here. The point of the dependency
being live is to find out the day they stop fitting together — which only works
if something notices.

So the claim is pinned in both directions. Every figure the README quotes has
to appear in the payload `paper-to-live run --json` produces, and every row
label has to still be in the document, which is the other way a claim
disappears: somebody deletes the row.

One direction is deliberately not attempted. Scanning the README for a number
and comparing it to the measurement cannot tell which number it found: this
page quotes 0.82, 0.70, 0.35 and 0.27 within a few lines of each other, and a
check looking for "some number near here" can pass against the wrong one. The
forward direction plus the row labels catches a figure that moved and a row
that vanished, which is what matters.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from paper_to_live.pipeline import run
from paper_to_live.types import Settings

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def payload() -> dict[str, Any]:
    """The default run, as the command line emits it.

    Called in process rather than over a subprocess: the figures are the same
    object the CLI serialises, and the whole pipeline is eight seconds of work
    that the rest of this suite already pays for once.
    """
    result = run(Settings())
    return json.loads(json.dumps(result.as_dict(), allow_nan=False))


#: Row labels from the evidence table. Presence is what is checked, not the
#: value beside it — see the module docstring for why that direction is the
#: wrong one to scan for.
ROWS = (
    "The search run against a market with no exploitable structure",
    "0.95 shown to be reachable at all, so the row above is evidence",
    "The erosion column, as an identity rather than an arrangement",
    "322 crossover rules, counted as independent trials",
    "Recovered positions against the return series they came from",
    "The bootstrapped curve repricing the quotes it was built from",
    "Published impact coefficients used as averages rather than as peaks",
    "The financing haircut by three routes, one of them another package",
)


@pytest.mark.parametrize("row", ROWS)
def test_the_evidence_table_still_has_the_row(row: str) -> None:
    assert row in README


def test_the_table_has_exactly_the_rows_that_are_pinned() -> None:
    """A row added to the table and never pinned would otherwise be free.

    The table is found by its heading rather than by scanning every pipe in the
    document, because the README carries two other tables — the four stages and
    the module layout — and counting all of them would make this pass for the
    wrong reason.
    """
    section = README.split("## What is checked, and against what", 1)[1]
    section = section.split("\n## ", 1)[0]
    rendered = [
        line
        for line in section.splitlines()
        if line.startswith("| ")
        and not line.startswith("| ---")
        and line != "| Check | Result |"
    ]
    assert len(rendered) == len(ROWS)
    for row, line in zip(ROWS, rendered, strict=True):
        assert line.startswith(f"| {row} |")


def test_the_erosion_column_is_an_identity(payload: dict[str, Any]) -> None:
    """Paper less execution less financing is the surviving figure, exactly.

    The README prints the four as a column with a rule under it, which is a
    claim that they are a decomposition. Zero rather than nearly zero: the
    surviving figure is computed as that subtraction, so anything else would
    mean the page is printing a different quantity from the one it derives.
    """
    erosion = payload["erosion"]
    residue = (
        erosion["paper_sharpe_annual"]
        - erosion["execution_drag"]
        - erosion["funding_drag"]
        - erosion["surviving_sharpe_annual"]
    )
    assert residue == 0.0
    assert "residue 0.0" in README

    # And the quoted figures are the quoted figures.
    for key, quoted in (
        ("paper_sharpe_annual", "0.8226"),
        ("execution_drag", "0.2039"),
        ("funding_drag", "0.2732"),
        ("surviving_sharpe_annual", "0.3455"),
    ):
        assert f"{erosion[key]:.4f}" == quoted, f"{key} moved"
        assert quoted in README


def test_the_headline_figures_are_the_ones_quoted(payload: dict[str, Any]) -> None:
    """The paper Sharpe ratio, the deflation, and the survival fraction."""
    erosion = payload["erosion"]
    selection = payload["selection"]
    assert f"{erosion['paper_sharpe_annual']:.2f}" == "0.82"
    assert f"{selection['deflated_sharpe']:.2f}" == "0.70"
    assert f"{erosion['fraction_surviving']:.0%}" == "42%"
    for quoted in ("paper Sharpe 0.82", "deflated to 0.70"):
        assert quoted in README


def test_the_search_size_and_its_effective_count(payload: dict[str, Any]) -> None:
    """322 rules, 35 of them independent.

    The effective count comes back as 35.000000000000050 rather than 35, since
    it is a sum over an eigenvalue spectrum. The README rounds it and this is
    what says the rounding is honest.
    """
    selection = payload["selection"]
    assert selection["candidates"] == 322
    assert selection["effective_trials"] == pytest.approx(35.0, abs=1e-9)
    assert "322 crossover rules" in README
    assert "35.0 effective, by the eigenvalue method" in README


def test_the_reconstruction_is_exactly_exact(payload: dict[str, Any]) -> None:
    """Zero, and zero ambiguous days, over the sample the README names."""
    selection = payload["selection"]
    assert selection["reconstruction_worst_error"] == 0.0
    assert selection["reconstruction_ambiguous_days"] == 0
    assert payload["settings"]["days"] == 1008
    assert "worst error exactly 0.0 over 1008 days, 0 of them ambiguous" in README


def test_the_repricing_error_is_inside_the_bound_the_readme_states() -> None:
    """A bound, not digits.

    The README says 5.6e-17 and explains that the digits of a root-found
    residue are not portable between interpreters. So the check is the bound
    that sentence implies rather than the rendering: anything under 1e-15
    reprices the curve on its own quotes and nothing weaker does.
    """
    result = run(Settings())
    assert abs(result.funding.worst_repricing_error) < 1e-15
    assert "5.6e-17 worst error, 4 instruments" in README


def test_the_peak_coefficient_overstatement(payload: dict[str, Any]) -> None:
    """Published coefficients are peaks, and using them as averages doubles it.

    The ratio is the content of the row: it is not that 415 is a large number,
    it is that 415 is what you charge by reading a peak coefficient as an
    average when the honest figure is 207.
    """
    execution = payload["execution"]
    assert round(execution["peak_overstatement_bps"]) == 415
    assert round(execution["annual_cost_bps"]) == 207
    assert execution["peak_overstatement_bps"] == pytest.approx(
        2 * execution["annual_cost_bps"], rel=1e-12
    )
    assert "415 bps against the 207 bps actually charged" in README


def test_the_seed_sweep_the_readme_cites_is_the_one_the_suite_runs() -> None:
    """The page says six seeds. The sweep has to actually be six.

    This is the row that carries the project's conclusion, and "at every seed
    swept" is only worth reading if the sweep is wider than one. Counted out of
    the test file rather than restated, so narrowing the sweep fails here.
    """
    sweep = (ROOT / "tests" / "test_selection.py").read_text(encoding="utf-8")
    match = re.search(r'parametrize\("seed", \[([0-9, ]+)\]\)', sweep)
    assert match is not None, "the seed sweep is no longer a parametrised list"
    seeds = [int(part) for part in match.group(1).split(",")]
    assert len(seeds) == 6
    assert "six seeds" in README


def test_the_suite_size_the_readme_claims_is_about_right() -> None:
    """A loose bound, on purpose.

    An exact count fails on every commit that adds a test, which trains people
    to update the number without reading it. A quarter either way catches a
    figure that has gone properly stale and tolerates ordinary growth.
    """
    import subprocess
    import sys

    match = re.search(r"Behind them: ([\d,]+) tests", README)
    assert match is not None, "the README no longer says how large the suite is"
    claimed = int(match.group(1).replace(",", ""))

    finished = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "-q",
            "--collect-only",
            "tests",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    collected = re.search(r"(\d+) tests? collected", finished.stdout)
    if collected is None:  # pragma: no cover - no checkout to collect from
        pytest.skip(f"could not collect: {finished.stdout[-400:]}")

    actual = int(collected.group(1))
    low = f"the README claims {claimed}, the suite is {actual}"
    assert claimed >= actual * 0.75, low
    assert claimed <= actual * 1.25, low
