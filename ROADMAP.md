# Roadmap

Each phase leaves the repository runnable. A phase is done when its work is on
`main`, exercised end to end, and reflected in the README.

## Phase 1 — The candidate set

- [x] A reproducible parameter sweep that produces many candidate strategies
- [x] Reconstruct the winner's positions and prove they reproduce its returns
- [x] Selection: best-of, effective trials, deflated Sharpe, PBO

## Phase 2 — Continuous integration

- [x] Test matrix across supported interpreters
- [x] Type check and lint
- [x] The worked example runs as a gate, not a report

## Phase 3 — What execution costs

- [x] Turn position changes into parent orders against a stated ADV
- [x] Price them under a calibrated impact law
- [x] A net-of-cost return series, and the drag in basis points a year

## Phase 4 — What the book risks

- [x] Value at risk and expected shortfall of the net series
- [x] Drawdown, and how much of the tail the sample actually contains

## Phase 5 — What the capital costs

- [x] Bootstrap a discount curve from a quoted screen
- [x] The financing rate over the backtest horizon
- [x] The Sharpe ratio in excess of it

## Phase 6 — One command, one table

- [x] A single entry point that runs all four stages
- [x] The erosion table as the default output, JSON on request
- [x] Every stage callable on its own

## Phase 7 — Guards

- [x] The published figures reproduce, and the check fails if they move
- [x] The conclusion is stable across seeds, asserted rather than claimed
- [x] `--help` renders for every command and every argument documents itself

## Phase 8 — Distribution

- [ ] Depend on released versions of the libraries instead of building them —
      waiting on the four libraries having releases to depend on. The declared
      requirements are already the bounded ranges this needs; what is missing is
      anything on the index for them to resolve to
- [x] Release metadata and a tag-driven publish
- [x] Metadata checked by the suite rather than by the first person to install
      it: the version in two files, the licence reaching the artefact and not
      just the repository, `py.typed` inside the package, the console script
      pointing at the function that implements it
- [x] The dependency list pinned to a shape — four bounded ranges, no direct
      references — since a `git+https` requirement is refused on upload and so
      cannot be what a publishable distribution says
- [x] Each declared library walked from the requirement through the installed
      distribution to the module, because two of the four do not import under
      the name the index serves them by
- [x] A tag-against-declared-version guard, `twine check --strict`, and the
      sdist and the wheel each installed into a clean environment and run — two
      code paths, so checking one proves nothing about the other
- [x] The two artefacts' tables diffed against each other, because a claim that
      depends on which artefact you installed is not a claim
- [x] Publishing split into a job that checks out no code and runs none, holding
      `id-token: write` and nothing else, so no credential is stored anywhere
- [x] A gate in front of all of it asking the index whether the declared
      requirements resolve, so that tagging too early fails the build rather
      than shipping something uninstallable; verified against the index as it
      stands, where it exits on `holdout-backtest (from versions: none)`

## Phase 9 — A front page that says what it checked

- [x] A table of what was measured and against what, above the install line,
      so the output at the top of the page stops being a claim about itself
- [x] The row the project exists for first: the market's drift is zero, so the
      winner of 322 rules won by luck and the deflated Sharpe ratio is being
      measured against a *known answer* rather than against nothing
- [x] Its guard beside it, since an assertion no input can violate tests
      nothing — 0.95 shown to be attainable on the same sample length and the
      same trial dispersion
- [x] The identities named as identities: the erosion column adds up to zero
      and the recovered positions reproduce their own series to zero, neither
      of them "nearly"
- [x] The repricing error quoted as a bound, since the last bits a root finder
      lands on are not portable between interpreters
- [x] Every figure produced by `paper-to-live run --json`, which CI already
      runs against the built wheel, rather than by a new script
- [x] Pinned in three directions — a figure that moves, a row that is deleted,
      and a table row that is not among the pinned ones — with the table found
      by its heading, because this page carries two other tables and counting
      every pipe in it would pass for the wrong reason
- [x] The value direction deliberately not scanned: the page quotes 0.82,
      0.70, 0.35 and 0.27 within a few lines of each other, so a check looking
      for a number near a place can pass against the wrong one
- [x] The seed sweep's width counted out of the test file rather than
      restated, because "at every seed swept" is only worth reading if the
      sweep is wider than one


## Phase 10 — Three routes to the financing haircut

`FundingResult` reported the Sharpe ratio before financing, the ratio after it,
and the hurdle. The first two differ by the third, because the hurdle is
`zero / annual_volatility` and the drop is `daily * sqrt(252) / sd` — the same
number reached two ways inside one dataclass, with nothing asserting that they
agree. The report prints them a row apart, where a reader would never see them
part company.

- [x] The internal identity asserted, so the two routes cannot drift
- [x] A third route from outside this package: `holdout.financing_impact`,
      a different implementation of the same correction
- [x] A fourth from its closed form `rate / volatility`, whose residual has to
      be zero here because the stage reads one point off the curve for the
      whole horizon
- [x] All of them checked at three valuation dates rather than at the one the
      front page prints
- [x] The continuous-rate convention measured rather than argued: charging
      `zero / 252` where an arithmetic return wants `expm1(zero / 252)` costs
      1.3e-05 of annualised Sharpe against a haircut of 0.224
- [x] Five ways of breaking the stage confirmed to fail first, four or five
      tests each
- [x] A row on the front page, since this is evidence rather than new surface

Nothing new is computed in this phase. What it adds is that the figure the
report leads with — the financing line of the erosion column — is now pinned
against an implementation in another package, which is a stronger statement
than this repository can make about itself. The agreement is 3e-16.

## Phase 11 — A front page, drawn from the run

- [x] A generated site: the generator returns strings and touches no
      filesystem, so the tests call it directly and one thin entry point
      writes `site/`
- [x] The erosion column *drawn* — a waterfall from the paper figure through
      execution and financing to what survives, as inline SVG from the
      pipeline's own payload, with the figure printed on every bar. A column of
      four numbers makes a reader do the subtraction; the chart does it for
      them, and the number stays because a bar height is an impression
- [x] The geometry checked against the arithmetic rather than looked at: each
      deduction starts where the previous bar ended, each is the right number
      of pixels for what it takes, and the survivor's top is where the last
      deduction stopped. A chart that renders cleanly and shows the wrong shape
      looks exactly like one that is right
- [x] Two hues, validated rather than chosen — lightness band, chroma floor,
      colour-vision separation, normal-vision separation and contrast, against
      the light and the dark chart surface separately — and neither hue
      load-bearing on its own, because every bar is named and carries a signed
      figure
- [x] One evidence gate and not two: the page renders the README's table, which
      the suite already pins to the payload in both directions, rather than
      deriving a second rendering of the same measurement
- [x] The report the command prints, on the page verbatim
- [x] Nine ways of breaking the page, nine caught — after a first sweep of nine
      caught eight. The miss was that the level-versus-cost assertion checked
      the CSS class rather than the fill, so painting every bar one hue passed:
      the class is metadata and the fill is what a reader sees

## Phase 12 — What the accounting leaves out

- [x] A known-gaps list, eleven lines, each verified against the code and each
      stated in terms of which way it moves the surviving Sharpe ratio — they
      all move it the same way, which is the reason the list is worth reading
- [x] The conventions that are choices rather than omissions named as such, in
      particular that financing is charged on the capital every day whatever
      the book was holding
- [x] A test pairing each line with a predicate, failing when a line goes
      missing, when a predicate does, when the list shrinks, when a bullet
      stops saying anything, and when a gap is closed
- [x] The suite size the README states recounted in a subprocess against a
      loose bound, after it was found claiming 100 tests against 118
