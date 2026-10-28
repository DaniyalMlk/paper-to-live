"""The documentation site, generated from the pipeline rather than written beside it.

Three rules decide what is allowed on the page.

**Every figure comes from a run.** The page is built by running the pipeline
and reading its payload -- the same object ``paper-to-live run --json`` emits,
which CI runs against the built wheel and the suite reads back. Nothing here is
a number somebody typed, because a number typed on a page is a number that will
be wrong in a month.

**There is one evidence gate, not two.** The README's table is already a gated
artefact: ``tests/test_readme_evidence.py`` pins every figure in it forwards
against the payload, and pins the row set exactly. So the page renders *that*
table rather than deriving a second one from the same payload, because two
renderings of one measurement are two things that can disagree.
``tests/test_docs.py`` asserts the page's rows are exactly the pinned ones.

**The erosion column is drawn.** It is the argument this repository exists to
make -- 0.82 of paper Sharpe walked down to what survives -- and a column of
four numbers makes a reader do the subtraction. The waterfall does it for them,
with the figure printed on every bar, because a bar height is an impression and
the number is the claim.

The site is two files, and ``site/`` is gitignored: the repository holds this
generator, not its output.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paper_to_live import __version__
from paper_to_live.pipeline import run
from paper_to_live.report import erosion_table
from paper_to_live.types import Settings

ROOT = Path(__file__).resolve().parent.parent
SOURCE = "https://github.com/DaniyalMlk/paper-to-live"
DISTRIBUTION = "paper-to-live"

#: The libraries the pipeline is assembled from, in the order the stages run.
#: Each is a separate repository and a separate distribution; this one is the
#: thing that puts them together, which is the only claim it makes.
STAGES: tuple[tuple[str, str, str], ...] = (
    ("Selection", "holdout-backtest", "what the search inflated"),
    ("Execution", "slippage-tca", "what trading it costs"),
    ("Risk", "shortfall", "what the book risks"),
    ("Funding", "tenor-curves", "what the capital costs"),
)


@dataclass(frozen=True)
class Measured:
    """Everything the page is built from, measured once."""

    payload: dict[str, Any]
    report: str
    rows: tuple[tuple[str, str], ...]


def readme_rows() -> tuple[tuple[str, str], ...]:
    """The evidence table, read out of the README that already gates it.

    Not re-derived from the payload. The README's rows are pinned by
    ``tests/test_readme_evidence.py`` -- every figure in them has to appear in
    the payload, and the row set has to be exactly the one listed there -- so
    rendering those rows means the page inherits that gate instead of adding a
    second one that can drift from it.
    """
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    section = text.split("## What is checked, and against what", 1)
    if len(section) != 2:
        raise RuntimeError("the README no longer has an evidence section")
    # Stop at the next heading. Taking everything after this one swept up the
    # tables in the sections below it and produced a twenty-row evidence table,
    # which is the kind of mistake a count catches and prose does not.
    rest = section[1].split("\n## ", 1)[0]
    rows: list[tuple[str, str]] = []
    for line in rest.splitlines():
        if not line.startswith("| ") or line.startswith("| ---"):
            continue
        cells = [cell.strip() for cell in line[1:-1].split(" | ")]
        if len(cells) != 2:
            raise RuntimeError(f"an evidence row is not two cells: {line}")
        if cells[0] == "Check":
            continue
        rows.append((cells[0], cells[1]))
    if not rows:
        raise RuntimeError("the README's evidence table has no rows in it")
    return tuple(rows)


def measure() -> Measured:
    """Run the pipeline once and take everything off it."""
    pipeline = run(Settings())
    return Measured(
        payload=pipeline.as_dict(),
        report=erosion_table(pipeline),
        rows=readme_rows(),
    )


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def _code(text: str) -> str:
    """Backticks to ``<code>``, after escaping."""
    out: list[str] = []
    for index, part in enumerate(text.split("`")):
        out.append(part if index % 2 == 0 else f"<code>{part}</code>")
    return "".join(out)


# ------------------------------------------------------------ the waterfall


#: Two hues and nothing else. The levels -- what the backtest said and what
#: survives -- are the subject; the two deductions are the other thing. Both
#: validated against the light and the dark chart surface for lightness band,
#: chroma, CVD separation (worst adjacent pair dE 24.7 protan on light, 26.8 on
#: dark), normal-vision separation and contrast, rather than chosen by eye.
LEVEL_LIGHT, COST_LIGHT = "#2a78d6", "#eb6834"
LEVEL_DARK, COST_DARK = "#3987e5", "#d95926"


def waterfall(payload: dict[str, Any]) -> str:
    """The erosion column, drawn.

    A waterfall rather than four bars from zero, because the reader's question
    is what happened *between* the first number and the last one, and four bars
    from zero asks them to do the subtraction themselves.

    Every bar carries its own figure. A bar height is an impression; the number
    is the claim, and the claim is what the gate checks. The deductions are
    labelled with what they cost as well as with the Sharpe they took, because
    "0.20 of Sharpe" and "207 basis points a year" are the same fact said to
    two different readers.
    """
    erosion = payload["erosion"]
    paper = float(erosion["paper_sharpe_annual"])
    execution = float(erosion["execution_drag"])
    funding = float(erosion["funding_drag"])
    surviving = float(erosion["surviving_sharpe_annual"])
    fraction = float(erosion["fraction_surviving"])
    cost_bps = float(payload["execution"]["annual_cost_bps"])
    zero = float(payload["funding"]["zero_rate"])
    horizon = float(payload["funding"]["horizon_years"])

    # (label, bottom, top, kind, figure, note)
    bars = [
        ("Paper", 0.0, paper, "level", f"{paper:+.2f}", "what the backtest said"),
        (
            "Execution",
            paper - execution,
            paper,
            "cost",
            f"-{execution:.2f}",
            f"{cost_bps:.0f} bps a year",
        ),
        (
            "Financing",
            surviving,
            paper - execution,
            "cost",
            f"-{funding:.2f}",
            f"{zero * 100:.2f}% at {horizon:.0f}y",
        ),
        (
            "Surviving",
            0.0,
            surviving,
            "level",
            f"{surviving:+.2f}",
            f"{fraction * 100:.0f}% of the paper figure",
        ),
    ]

    # Geometry. A fixed viewBox scaled by the page, so the chart is sharp at
    # any width and needs no script to lay itself out.
    width, height = 720.0, 320.0
    left, right, top, floor = 16.0, 16.0, 34.0, 74.0
    plot = height - top - floor
    span = max(paper, 0.001)
    column = (width - left - right) / len(bars)
    bar_width = column * 0.46

    def y_of(value: float) -> float:
        return top + plot * (1 - value / span)

    marks: list[str] = []
    for index, (label, low, high, kind, figure, note) in enumerate(bars):
        centre = left + column * index + column / 2
        x = centre - bar_width / 2
        y = y_of(high)
        tall = max(y_of(low) - y, 2.0)
        fill = "var(--level)" if kind == "level" else "var(--cost)"
        # 4px rounded ends on the bar, and a 2px gap between a deduction and
        # the level it comes off, so adjacent fills never touch.
        marks.append(
            f'<g class="bar bar--{kind}">'
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" '
            f'height="{tall:.1f}" rx="4" fill="{fill}" />'
            f'<text class="figure" x="{centre:.1f}" y="{y - 10:.1f}" '
            f'text-anchor="middle">{esc(figure)}</text>'
            f'<text class="name" x="{centre:.1f}" y="{height - floor + 22:.1f}" '
            f'text-anchor="middle">{esc(label)}</text>'
            f'<text class="note" x="{centre:.1f}" y="{height - floor + 40:.1f}" '
            f'text-anchor="middle">{esc(note)}</text>'
            f"</g>"
        )
        # The connector to the next bar: where this one left the reader.
        if index < len(bars) - 1:
            hand_off = low if kind == "cost" else high
            next_left = left + column * (index + 1) + column / 2 - bar_width / 2
            marks.append(
                f'<line class="connector" x1="{x + bar_width:.1f}" '
                f'y1="{y_of(hand_off):.1f}" x2="{next_left:.1f}" '
                f'y2="{y_of(hand_off):.1f}" />'
            )

    baseline = y_of(0.0)
    return (
        f'<figure class="chart">\n'
        f'<svg viewBox="0 0 {width:.0f} {height:.0f}" role="img" '
        f'aria-label="Sharpe ratio from {paper:.2f} on paper to {surviving:.2f} '
        f'surviving, after {execution:.2f} of execution and '
        f'{funding:.2f} of financing">\n'
        f'<line class="axis" x1="{left:.0f}" y1="{baseline:.1f}" '
        f'x2="{width - right:.0f}" y2="{baseline:.1f}" />\n'
        + "\n".join(marks)
        + "\n</svg>\n"
        + '<figcaption>Annualised Sharpe ratio. Blue is a level, orange is what '
        "was taken off it; every bar carries its own figure because a bar height "
        "is an impression and the number is the claim.</figcaption>\n</figure>"
    )


# ------------------------------------------------------------- the front page


def _evidence_table(rows: tuple[tuple[str, str], ...]) -> str:
    body = "\n".join(
        f"<tr><td>{_code(esc(check))}</td><td>{_code(esc(result))}</td></tr>"
        for check, result in rows
    )
    return (
        '<table class="evidence">\n'
        "<thead><tr><th>Check</th><th>Result</th></tr></thead>\n"
        f"<tbody>\n{body}\n</tbody>\n</table>"
    )


def _stages() -> str:
    items = "\n".join(
        f'<li><span class="stage__name">{esc(name)}</span>'
        f'<span class="stage__lib"><code>{esc(library)}</code></span>'
        f'<span class="stage__job">{esc(job)}</span></li>'
        for name, library, job in STAGES
    )
    return f'<ol class="stages">\n{items}\n</ol>'


def landing(measured: Measured) -> str:
    payload = measured.payload
    erosion = payload["erosion"]
    selection = payload["selection"]
    risk = payload["risk"]
    settings = payload["settings"]

    paper = float(erosion["paper_sharpe_annual"])
    surviving = float(erosion["surviving_sharpe_annual"])
    deflated = float(selection["deflated_sharpe"])
    candidates = int(selection["candidates"])
    effective = float(selection["effective_trials"])
    drawdown = float(risk["max_drawdown"])
    underwater = int(risk["longest_underwater_days"])
    days = int(settings["days"])

    body = f"""<header class="masthead col--wide">
  <a class="mark" href="./"><span class="mark__glyph"
    aria-hidden="true"></span>paper&nbsp;to&nbsp;live</a>
  <nav class="masthead__nav">
    <a href="#erosion">Where it went</a>
    <a href="#report">The run</a>
    <a href="#evidence">What is checked</a>
    <a href="#install">Install</a>
    <a href="{esc(SOURCE)}">Source</a>
  </nav>
</header>

<main>

<section class="lede col--wide">
  <h1>The backtest said {paper:.2f}. A desk would underwrite&nbsp;{surviving:.2f}.</h1>
  <p class="standfirst">One command walks a backtested strategy from its paper
  Sharpe ratio to the number that survives contact with a funded book: what the
  search inflated, what execution takes, what the capital costs, and what the
  position would have asked a person to sit through. It is assembled from four
  separate libraries, and the point of it is that the deductions are
  <em>measured</em> rather than assumed.</p>
  <p class="actions">
    <a class="cta" href="#erosion">See where it went</a>
    <a class="plain" href="{esc(SOURCE)}">Read the source</a>
  </p>
</section>

<section id="erosion" class="erosion">
  <div class="col--wide">
    <h2>Where the Sharpe ratio went</h2>
    <p>Run against a simulated market with <strong>no exploitable structure in
    it</strong> &mdash; the generator&rsquo;s drift term is zero, so whatever
    wins a search over {candidates} rules won by luck. That is the point: it
    makes every figure below a measurement against a known answer rather than a
    result.</p>
    {waterfall(payload)}
    <p class="aside"><strong>And then the honest question.</strong> After
    correcting for {candidates} trials &mdash; {effective:.0f} of them
    effectively independent, by the eigenvalue method &mdash; the probability
    that the true Sharpe ratio is above zero comes back at
    <strong>{deflated:.2f}</strong>. The threshold worth caring about is 0.95.
    A winner found by searching a market with nothing in it should not clear
    it, and does not; a real edge of the same size over the same
    {days:,} days does, which is what makes the first statement evidence rather
    than a tautology.</p>
    <p class="aside"><strong>What it would have taken to hold.</strong> A
    {drawdown * 100:.1f}% drawdown and {underwater} days under water, on the
    surviving book. The two numbers nobody puts in a pitch and everybody finds
    out about later.</p>
  </div>
</section>

<section id="report" class="report col--wide">
  <h2>The run, as the command prints it</h2>
  <p>Not a description of the output. This was printed when the page was built,
  by the same code path the command line uses, from the default settings.</p>
  <pre class="terminal"><code>$ paper-to-live run

{esc(measured.report)}</code></pre>
</section>

<section class="assembly col--wide">
  <h2>Four libraries, one table</h2>
  <p>Each stage is a separate repository and a separate distribution. This one
  does not reimplement any of them &mdash; it is the thing that puts them
  together, and that is the whole claim it makes. The identities it reports are
  checked across the seam rather than inside it: the financing haircut is
  computed here, read off the curve, and taken from a fourth package, and the
  three agree to 3e-16.</p>
  {_stages()}
</section>

<section id="evidence" class="evidence-section col--wide">
  <h2>What is checked, and against what</h2>
  <p>Everything above is this repository&rsquo;s own output, which is the
  easiest kind of number to produce and the hardest to believe. So here is what
  each line was checked against. Every figure is produced by
  {_code("`paper-to-live run --json`")}, which CI runs against the built wheel
  and which the suite reads back, so a figure that moves fails on the commit
  that moved it.</p>
  {_evidence_table(measured.rows)}
  <p class="aside"><strong>The first row is the one the project exists
  for.</strong> The simulated market has nothing in it to find, so the deflated
  Sharpe ratio is a measurement against a known answer: the true ratio is zero,
  and the honest report of a {paper:.2f} winner is a coin flip&rsquo;s worth of
  evidence that it is not worthless. Coming back with {deflated:.2f} is the
  library being right rather than the library producing a number.</p>
  <p class="aside"><strong>The second row guards the first.</strong> An
  assertion no input can violate tests nothing, so 0.95 has to be shown
  attainable on the same sample length and the same trial dispersion &mdash;
  otherwise &ldquo;never above 0.95&rdquo; is a statement about the threshold
  rather than about the market.</p>
  <p class="aside"><strong>This page renders the README&rsquo;s table, not a
  second copy of it.</strong> Those rows are already pinned to the payload in
  both directions by the suite. Deriving a second rendering from the same
  measurement would be two things that can disagree, and the one on the public
  page would be the one nobody notices.</p>
</section>

<section id="install" class="install col--wide">
  <h2>The first minute</h2>
  <pre><code>pip install {esc(DISTRIBUTION)}</code></pre>
  <pre><code>paper-to-live run            # the table above
paper-to-live run --json     # every figure on it, as data</code></pre>
  <p>That pulls the four libraries with it and runs end to end. Python 3.10 or
  newer. Version {esc(__version__)}.</p>
  <p class="aside">The market is simulated on purpose and must stay that way.
  A generator with an edge in it would make every figure on this page a
  statement about the generator.</p>
</section>

</main>

<footer class="foot col--wide">
  <p>paper to live, published as <code>{esc(DISTRIBUTION)}</code>. Built by
  running the pipeline, so no figure on this page was typed by hand.
  <a href="{esc(SOURCE)}">Source</a>.</p>
</footer>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>paper to live &middot; what a backtest is worth after costs</title>
<meta name="description" content="A backtested strategy walked from its paper \
Sharpe ratio to what a funded book would underwrite: selection bias, execution \
cost, tail risk and financing, each measured rather than assumed.">
<meta name="color-scheme" content="light dark">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' \
viewBox='0 0 16 16'%3E%3Crect width='16' height='16' rx='3' fill='%231a1a19'/%3E\
%3Crect x='2.5' y='3' width='2.6' height='10' fill='%232a78d6'/%3E\
%3Crect x='6.7' y='6' width='2.6' height='7' fill='%23eb6834'/%3E\
%3Crect x='10.9' y='9' width='2.6' height='4' fill='%232a78d6'/%3E%3C/svg%3E">
<link rel="stylesheet" href="style.css">
</head>
<body>
{body}
</body>
</html>
"""


STYLE = """/*
 * Generated by docs/pages.py.
 *
 * Two hues, both validated rather than chosen: a level hue and a cost hue,
 * checked for lightness band, chroma floor, colour-vision separation,
 * normal-vision separation and contrast against each chart surface, in light
 * and in dark separately. Dark is a selected palette and not an inverted one.
 * Everything else is ink on paper, because the only place colour carries
 * meaning here is the waterfall.
 */

:root {
  color-scheme: light dark;

  --surface: #fcfcfb;
  --canvas: #f6f5f2;
  --sunken: #efeeea;
  --rule: #e2e0da;
  --rule-strong: #cbc9c1;
  --ink: #0b0b0b;
  --ink-soft: #52514e;
  --ink-mute: #7b7a74;

  --level: #2a78d6;
  --cost: #eb6834;

  --font: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI",
    "Helvetica Neue", Arial, sans-serif;
  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;

  --measure: 38rem;
  --wide: 60rem;
  --gutter: 1.25rem;
  --rail: max(var(--gutter), 50% - var(--wide) / 2);
}

@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    --surface: #1a1a19;
    --canvas: #141413;
    --sunken: #1f1f1e;
    --rule: #2e2e2c;
    --rule-strong: #45453f;
    --ink: #f0efec;
    --ink-soft: #c3c2b7;
    --ink-mute: #8d8c84;

    --level: #3987e5;
    --cost: #d95926;
  }
}

.col--wide { padding-inline: var(--rail); }

/*
 * Prose is capped at the measure by a child selector, never on the element
 * carrying the rail: with border-box sizing the padding would eat the
 * max-width and leave the text a few words across.
 */
.lede > *, .erosion p, .report > *, .assembly > p, .install > *, .foot > p,
.evidence-section > p { max-width: var(--measure); }
.lede h1 { max-width: 19ch; }

*, *::before, *::after { box-sizing: border-box; }

html { -webkit-text-size-adjust: 100%; }

body {
  margin: 0;
  background: var(--canvas);
  color: var(--ink);
  font-family: var(--font);
  font-size: 1.0625rem;
  line-height: 1.62;
  -webkit-font-smoothing: antialiased;
}

a { color: var(--level); text-underline-offset: 2px; }
a:hover { color: var(--ink); }

code, pre { font-family: var(--mono); font-variant-numeric: tabular-nums; }
code { font-size: 0.9em; }

pre {
  background: var(--surface);
  border: 1px solid var(--rule);
  border-radius: 7px;
  padding: 0.9rem 1.05rem;
  overflow-x: auto;
  font-size: 0.8125rem;
  line-height: 1.55;
  margin: 1.05rem 0;
  max-width: var(--measure);
}

pre code { font-size: inherit; }

h1, h2 { letter-spacing: -0.022em; font-weight: 640; text-wrap: balance; }

/* -- masthead ------------------------------------------------------------ */

.masthead {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem 1.5rem;
  align-items: baseline;
  justify-content: space-between;
  padding-block: 1.35rem;
  border-bottom: 1px solid var(--rule);
}

.mark {
  font-weight: 650;
  font-size: 1.0625rem;
  color: var(--ink);
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: 0.55rem;
}

.mark__glyph {
  width: 0.9rem;
  height: 0.9rem;
  border-radius: 2px;
  background: linear-gradient(90deg, var(--level) 0 55%, var(--cost) 55% 100%);
  flex: none;
}

.masthead__nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem 1.2rem;
  font-size: 0.9375rem;
}
.masthead__nav a { color: var(--ink-soft); text-decoration: none; }
.masthead__nav a:hover { color: var(--level); }

/* -- lede ---------------------------------------------------------------- */

.lede { padding-block: 4rem 2.4rem; }

h1 { margin: 0 0 1.05rem; font-size: clamp(1.9rem, 5.4vw, 2.85rem); line-height: 1.09; }

.standfirst { margin: 0; font-size: 1.125rem; color: var(--ink-soft); }

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.7rem 1.2rem;
  align-items: center;
  margin: 1.8rem 0 0;
}

.cta {
  background: var(--ink);
  color: var(--canvas);
  padding: 0.58rem 1.1rem;
  border-radius: 6px;
  font-size: 0.9375rem;
  font-weight: 550;
  text-decoration: none;
}

.cta:hover { background: var(--level); color: #ffffff; }

.plain { font-size: 0.9375rem; color: var(--ink-soft); }

/* -- the chart ----------------------------------------------------------- */

.erosion {
  background: var(--sunken);
  border-block: 1px solid var(--rule);
  padding-block: 3rem;
}

h2 { margin: 0 0 1rem; font-size: 1.45rem; }
.erosion p, .report p, .evidence-section p, .install p, .assembly p {
  margin: 0 0 1rem;
}

.chart {
  margin: 1.8rem 0 1.6rem;
  background: var(--surface);
  border: 1px solid var(--rule);
  border-radius: 10px;
  padding: 0.6rem 0.4rem 0.2rem;
}

.chart svg { display: block; width: 100%; height: auto; }

.chart .axis { stroke: var(--rule-strong); stroke-width: 1; }
.chart .connector {
  stroke: var(--rule-strong);
  stroke-width: 2;
  stroke-dasharray: 3 3;
}

.chart .figure {
  fill: var(--ink);
  font-family: var(--mono);
  font-size: 17px;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}

.chart .name {
  fill: var(--ink);
  font-family: inherit;
  font-size: 14px;
  font-weight: 550;
}

.chart .note { fill: var(--ink-mute); font-family: inherit; font-size: 12px; }

.chart figcaption {
  color: var(--ink-mute);
  font-size: 0.8125rem;
  line-height: 1.5;
  padding: 0.5rem 0.9rem 0.7rem;
  max-width: 44rem;
}

/* -- sections ------------------------------------------------------------ */

.report { padding-block: 3rem 1rem; }
.assembly { padding-block: 1rem; }
.evidence-section { padding-block: 2.6rem; }
.install { padding-block: 1rem 3rem; }

.terminal {
  max-width: 52rem;
  font-size: 0.75rem;
  line-height: 1.5;
  background: var(--sunken);
}

.stages {
  list-style: none;
  margin: 1.4rem 0;
  padding: 0;
  max-width: 44rem;
}

.stages li {
  display: grid;
  grid-template-columns: 7rem 13rem 1fr;
  gap: 0.4rem 1rem;
  align-items: baseline;
  padding: 0.65rem 0;
  border-bottom: 1px solid var(--rule);
}

.stages li:last-child { border-bottom: 0; }
.stage__name { font-weight: 600; }
.stage__lib code { font-size: 0.8125rem; color: var(--ink-soft); }
.stage__job { color: var(--ink-soft); font-size: 0.9375rem; }

.evidence {
  width: 100%;
  border-collapse: collapse;
  margin: 1.5rem 0;
  font-size: 0.8125rem;
  background: var(--surface);
  border: 1px solid var(--rule);
}

.evidence th, .evidence td {
  text-align: left;
  vertical-align: top;
  padding: 0.55rem 0.8rem;
  border-bottom: 1px solid var(--rule);
  line-height: 1.5;
  font-family: var(--mono);
}

.evidence thead th {
  background: var(--sunken);
  font-weight: 600;
  color: var(--ink-soft);
  white-space: nowrap;
  font-size: 0.75rem;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.evidence tbody tr:last-child td { border-bottom: 0; }
.evidence td:first-child { color: var(--ink-soft); width: 42%; min-width: 15rem; }

.aside {
  font-size: 0.9375rem;
  color: var(--ink-soft);
  border-left: 2px solid var(--rule-strong);
  padding-left: 0.9rem;
}

.aside strong { color: var(--ink); font-weight: 600; }

/* -- footer -------------------------------------------------------------- */

.foot {
  border-top: 1px solid var(--rule);
  padding-block: 1.8rem 2.5rem;
  font-size: 0.875rem;
  color: var(--ink-mute);
}

.foot p { margin: 0; }

@media (max-width: 46rem) {
  .evidence { display: block; overflow-x: auto; }
  .stages li { grid-template-columns: 1fr; gap: 0.15rem; padding: 0.8rem 0; }
  .terminal { font-size: 0.625rem; }
  .chart .note { font-size: 11px; }
}
"""


def build_site(measured: Measured | None = None) -> dict[str, str]:
    """Every file the site is made of, keyed by the name it is published under.

    Pure: it runs the pipeline and returns strings, so ``tests/test_docs.py``
    can call it without a filesystem and ``docs/build.py`` is the only thing
    that writes anything.
    """
    taken = measure() if measured is None else measured
    return {"index.html": landing(taken), "style.css": STYLE}


#: Exported for the gate: the figures that must never reach the page as the
#: repr of a float rather than as a rounded figure.
RAW_FLOAT = re.compile(r"\d\.\d{6,}")
