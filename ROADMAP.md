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
- [ ] The worked example runs as a gate, not a report

## Phase 3 — What execution costs

- [ ] Turn position changes into parent orders against a stated ADV
- [ ] Price them under a calibrated impact law
- [ ] A net-of-cost return series, and the drag in basis points a year

## Phase 4 — What the book risks

- [ ] Value at risk and expected shortfall of the net series
- [ ] Drawdown, and how much of the tail the sample actually contains

## Phase 5 — What the capital costs

- [ ] Bootstrap a discount curve from a quoted screen
- [ ] The financing rate over the backtest horizon
- [ ] The Sharpe ratio in excess of it

## Phase 6 — One command, one table

- [ ] A single entry point that runs all four stages
- [ ] The erosion table as the default output, JSON on request
- [ ] Every stage callable on its own

## Phase 7 — Guards

- [ ] The published figures reproduce, and the check fails if they move
- [ ] The conclusion is stable across seeds, asserted rather than claimed
- [ ] `--help` renders for every command and every argument documents itself

## Phase 8 — Distribution

- [ ] Depend on released versions of the libraries instead of building them
- [ ] Release metadata and a tag-driven publish
