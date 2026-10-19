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

