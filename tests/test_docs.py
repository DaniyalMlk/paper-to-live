"""The site against the pipeline it describes.

The page is generated, so the usual failure -- a figure edited in the code and
not on the page -- cannot happen. The failures that *can* happen are these:

1. **The page quotes something no run produced.** A figure interpolated from
   somewhere else, or rounded differently from the report beside it.
2. **The page stops quoting something.** A row dropped from the evidence table,
   a bar dropped from the waterfall.
3. **The page draws something the numbers do not say.** A waterfall is a chart
   whose whole job is that the bars reconcile, so the geometry is checked
   against the arithmetic rather than looked at.

The third is the one worth the effort. A chart that renders without error and
shows the wrong shape looks exactly like a chart that is right, and no test
that only checks the page "contains 0.82" would notice.

One direction is deliberately not attempted: a scan of the page's free text
against the payload's floats. The payload carries full precision and the page
carries two decimal places, so a scan would either flag every numeral in a
sentence or be loosened until it flagged nothing. Figures are matched inside
the element they are rendered into instead.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "docs"))

from pages import (  # noqa: E402
    DISTRIBUTION,
    RAW_FLOAT,
    SOURCE,
    STAGES,
    build_site,
    measure,
    readme_rows,
    waterfall,
)


@pytest.fixture(scope="module")
def measured() -> Any:
    return measure()


@pytest.fixture(scope="module")
def files(measured: Any) -> dict[str, str]:
    return build_site(measured)


@pytest.fixture(scope="module")
def page(files: dict[str, str]) -> str:
    return files["index.html"]


# ------------------------------------------------------------- what it ships


def test_the_site_is_the_two_files_it_says_it_is(files: dict[str, str]) -> None:
    assert sorted(files) == ["index.html", "style.css"]
    assert len(files["style.css"]) > 3000


def test_the_page_links_its_stylesheet_and_fetches_nothing_else(page: str) -> None:
    assert '<link rel="stylesheet" href="style.css">' in page
    assert not re.search(r"https?://[^\"' ]*\.(?:css|js)", page)
    assert "<script" not in page.lower()
    assert "@import" not in page
    assert SOURCE in page
    assert f"pip install {DISTRIBUTION}" in page


def test_no_figure_reaches_the_page_as_a_full_precision_float(page: str) -> None:
    """The payload carries sixteen digits; a page that leaked one would show it.

    Interpolating `paper_sharpe_annual` straight out of the payload renders
    `0.8225893772775329`, which is not a Sharpe ratio anybody quotes and is the
    most likely way for a figure to arrive on the page wrong-looking rather
    than wrong.
    """
    leaked = RAW_FLOAT.findall(page)
    assert leaked == [], leaked


# ----------------------------------------- the evidence table, gated once


def test_the_page_renders_exactly_the_rows_the_readme_pins(
    page: str, measured: Any
) -> None:
    # The README's rows are pinned to the payload by test_readme_evidence.py,
    # forwards and as an exact set. This asserts the page renders that table
    # and not a second derivation of the same measurement.
    from test_readme_evidence import ROWS  # the labels that file pins

    labels = tuple(check for check, _ in measured.rows)
    assert labels == ROWS
    body = page.split('<table class="evidence">', 1)[1].split("</table>", 1)[0]
    assert body.count("<tr>") == len(ROWS) + 1  # the header is a row too
    assert body.count("<td>") == len(ROWS) * 2


def test_each_row_is_rendered_whole(page: str, measured: Any) -> None:
    import html as html_module

    def rendered(text: str) -> str:
        escaped = html_module.escape(text, quote=True)
        out: list[str] = []
        for index, part in enumerate(escaped.split("`")):
            out.append(part if index % 2 == 0 else f"<code>{part}</code>")
        return "".join(out)

    # Label and result in one string: asserting them separately passes on a
    # generator that paired the wrong result with a label.
    for check, result in measured.rows:
        assert f"<tr><td>{rendered(check)}</td><td>{rendered(result)}</td></tr>" in page


def test_the_readme_parse_stops_at_the_next_heading() -> None:
    """It did not, at first, and produced a twenty-row evidence table.

    The README has tables after this section. Taking everything below the
    heading swept them all up -- which a count caught and prose would not
    have.
    """
    rows = readme_rows()
    assert 5 <= len(rows) <= 12
    for check, result in rows:
        assert check and result
        assert not check.startswith("-")


# ------------------------------------------------------------- the waterfall


def _bars(svg: str) -> list[tuple[float, float]]:
    """Every bar as (top, height), in the order they are drawn."""
    return [
        (float(y), float(h))
        for y, h in re.findall(
            r'<rect x="[\d.]+" y="([\d.]+)" width="[\d.]+" height="([\d.]+)"', svg
        )
    ]


def test_the_waterfall_draws_one_bar_for_each_step(page: str, measured: Any) -> None:
    svg = waterfall(measured.payload)
    assert len(_bars(svg)) == 4
    assert svg in page
    for name in ("Paper", "Execution", "Financing", "Surviving"):
        assert f">{name}</text>" in svg


def test_the_bars_reconcile_the_way_the_arithmetic_does(measured: Any) -> None:
    """The geometry against the numbers, not against an eye.

    This is what a waterfall claims: each deduction starts where the previous
    bar ended, and the last bar's top is the first bar's top less both of them.
    A chart that renders cleanly and shows the wrong shape looks exactly like
    one that is right.
    """
    erosion = measured.payload["erosion"]
    svg = waterfall(measured.payload)
    bars = _bars(svg)
    paper, execution, financing, surviving = bars

    # Pixels per unit of Sharpe, taken off the first bar, which runs from the
    # baseline to the paper figure.
    scale = paper[1] / float(erosion["paper_sharpe_annual"])
    assert scale > 0

    # Each deduction hangs off where the one before it left the reader.
    assert execution[0] == pytest.approx(paper[0], abs=0.6)
    assert financing[0] == pytest.approx(execution[0] + execution[1], abs=0.6)
    # And the survivor's top is where the last deduction stopped.
    assert surviving[0] == pytest.approx(financing[0] + financing[1], abs=0.6)

    # The deductions are the right size, in pixels, for what they take.
    assert execution[1] == pytest.approx(
        float(erosion["execution_drag"]) * scale, abs=0.6
    )
    assert financing[1] == pytest.approx(
        float(erosion["funding_drag"]) * scale, abs=0.6
    )
    assert surviving[1] == pytest.approx(
        float(erosion["surviving_sharpe_annual"]) * scale, abs=0.6
    )

    # And the two levels really do differ, so none of the above is vacuous:
    # a run whose costs came to nothing would satisfy every line here with
    # four identical bars.
    assert surviving[1] < paper[1] * 0.8


def test_every_bar_carries_its_own_figure(measured: Any) -> None:
    erosion = measured.payload["erosion"]
    svg = waterfall(measured.payload)
    for figure in (
        f"{float(erosion['paper_sharpe_annual']):+.2f}",
        f"-{float(erosion['execution_drag']):.2f}",
        f"-{float(erosion['funding_drag']):.2f}",
        f"{float(erosion['surviving_sharpe_annual']):+.2f}",
    ):
        assert f">{figure}</text>" in svg


def test_the_chart_says_what_it_is_to_a_screen_reader(measured: Any) -> None:
    svg = waterfall(measured.payload)
    assert 'role="img"' in svg
    label = re.search(r'aria-label="([^"]+)"', svg)
    assert label is not None
    # The label carries the numbers, not just the word "chart".
    paper = float(measured.payload["erosion"]["paper_sharpe_annual"])
    assert f"{paper:.2f}" in label.group(1)


def test_colour_is_not_the_only_thing_telling_a_level_from_a_cost(
    measured: Any,
) -> None:
    # Two hues carry meaning here, so each bar is also named and direct-labelled
    # with a signed figure. A reader who cannot tell the hues apart still reads
    # "+0.82" against "Paper" and "-0.20" against "Execution".
    svg = waterfall(measured.payload)
    assert svg.count('class="name"') == 4
    assert svg.count('class="figure"') == 4
    # The fills, not the class names. A break sweep caught that: painting
    # every bar the level hue left the classes untouched and passed, and the
    # class is metadata while the fill is the thing a reader sees.
    fills = re.findall(r'<rect [^>]*fill="(var\(--\w+\))"', svg)
    assert len(fills) == 4
    assert len(set(fills)) == 2
    assert fills == ["var(--level)", "var(--cost)", "var(--cost)", "var(--level)"]
    assert svg.count('class="bar bar--level"') == 2
    assert svg.count('class="bar bar--cost"') == 2


# --------------------------------------------------- the report, and the rest


def test_the_report_on_the_page_is_the_one_the_command_prints(
    page: str, measured: Any
) -> None:
    import html as html_module

    assert html_module.escape(measured.report, quote=True) in page
    assert "$ paper-to-live run" in page


def test_the_stages_name_the_four_libraries_the_pipeline_depends_on(
    page: str,
) -> None:
    # Read with a regex rather than `tomllib`, which arrived in 3.11 and this
    # package supports 3.10. CI caught that; the container does not have 3.10
    # on it, so nothing local would have.
    manifest = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = manifest.split("dependencies = [", 1)[1].split("]", 1)[0]
    declared = {
        re.split(r"[<>=!\[]", item.strip().strip('",'))[0].strip()
        for item in block.splitlines()
        if item.strip().startswith('"')
    }
    assert "numpy" in declared
    named = {library for _, library, _ in STAGES}
    # numpy is a dependency and not a stage; every stage must be a dependency.
    assert named <= declared
    assert len(named) == 4
    for _, library, _ in STAGES:
        assert f"<code>{library}</code>" in page
