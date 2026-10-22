# paper-to-live

A backtested strategy, walked from its paper Sharpe ratio to the number a desk
would actually underwrite.

```console
$ pip install -e .
$ paper-to-live run
```

```
========================================================================
  FROM PAPER TO LIVE
========================================================================

  A search over 322 moving-average rules (35 effectively independent),
  1008 trading days, 50m of capital against 300m of daily volume.

------------------------------------------------------------------------
  WHERE THE SHARPE RATIO WENT
------------------------------------------------------------------------
  Paper (what the backtest said)           +0.82  rule 23/40
  less execution                           -0.20  207 bps a year
  less financing                           -0.27  2.83% at 4y
------------------------------------------------------------------------
  Surviving                                +0.35  42% of the paper figure

------------------------------------------------------------------------
  AND WHETHER ANY OF IT IS REAL
------------------------------------------------------------------------
  P(true Sharpe > 0) after search           0.70  wanted: > 0.95
  P(the ranking is overfit)                 0.31  0.50 is pure noise

------------------------------------------------------------------------
  WHAT IT WOULD HAVE TAKEN TO HOLD
------------------------------------------------------------------------
  Expected shortfall (99%, 1 day)        228 bps  from 11 tail days
  Deepest drawdown                         13.0%  372 days under water
  Turnover                                   42x  22 orders, largest 33% of a day

========================================================================

  CHECKS
------------------------------------------------------------------------
  Positions reproduce the backtest       0.0e+00  0 ambiguous days
  Curve reprices its own quotes          5.6e-17  4 instruments
  Peak impact would have overstated      415 bps  published coefficients are peaks
  Largest order, first half of day           61%  26 slices, 21.4 bps
```

That is the whole output. The rest of this page is what each line means.

## The question

A backtest reports the Sharpe ratio of whichever rule came first out of a
parameter search. Four things stand between that number and a funded book, and
each of them is a library in its own right:

| Stage | What it answers | Library |
| --- | --- | --- |
| Selection | How much of the winner is the search? | [holdout](https://github.com/DaniyalMlk/holdout) |
| Execution | What does putting it on cost? | [slippage](https://github.com/DaniyalMlk/slippage) |
| Risk | What would it have taken to hold? | [shortfall](https://github.com/DaniyalMlk/shortfall) |
| Funding | What does the capital cost? | [tenor](https://github.com/DaniyalMlk/tenor) |

This repository is the four of them in a line. It is a demonstration rather
than a product: the market it searches is simulated, and the screen the curve
is built from is a plausible one rather than a real one. What is not a
demonstration is the arithmetic between the stages, which is where the paper
number goes.

## What the run above says

The search tries 322 moving-average crossover rules over four years of a
simulated market **with nothing in it to find** — the generator's drift term is
set to zero, so every rule is trading noise. The best of them still comes back
with an annualised Sharpe ratio of 0.82, because the best of 322 draws is not a
draw.

From there:

- **Execution takes 0.20.** The winning rule reverses 21 times. Each reversal
  trades twice the book, which at 50m against 300m of daily volume is a third
  of a day's volume in one order, and the square-root law charges 20 basis
  points for it. Over four years that is 207 basis points a year.
- **Financing takes 0.27.** A Sharpe ratio is defined on returns in excess of a
  risk-free rate, and a backtest that subtracts nothing has set that rate to
  zero. The four-year point of the bootstrapped curve is 2.83%, and against the
  strategy's own volatility that is a hurdle of 0.27 before it earns anything.
- **0.35 survives**, 42% of what the backtest reported.

And then the part that matters more than any of it: **the deflated Sharpe ratio
is 0.70**. That is the probability the winner's true Sharpe ratio is above
*zero*, once the size of the search is accounted for. Not above 0.35. Above
zero. A coin-flip's worth of evidence that the strategy is not worthless, for
something that looked like a 0.82 four lines earlier.

## The design decision that mattered

The sweep hands back what each rule earned, not what it held — and the cost of
a strategy is set by how often and how far it moves, which a return series does
not show. Two rules with the same Sharpe ratio, one trading twice and one
trading two hundred times, are the same column of numbers and are not the same
strategy.

So the first thing the pipeline does after picking a winner is recover its
daily holdings by dividing each strategy return by that day's market return,
snap the result to a whole unit, and then **check that the recovered schedule
reproduces the series it came from**. The check raises rather than warning,
because every later stage prices the trades those positions imply: a silent
mismatch would be a cost number computed for a strategy nobody ran. The
`Positions reproduce the backtest` line above is that check, and on the default
run its worst error is exactly zero.

The one case it cannot see is a day the market did not move, where any holding
reproduces a zero return. Rather than absorb that, the recovery carries the
previous position forward and publishes the count of days it had to.

## Things that are easy to get wrong, and are checked here

- **Deflating by the number of rules rather than the number of bets.** A 23-day
  and a 25-day moving average are nearly the same strategy. Behind 322 rules
  there are 35 effectively independent trials, from the eigenvalues of their
  correlation matrix, and deflating by 322 would overstate the correction as
  badly as deflating by 1 understates it.
- **Charging the peak impact.** Published impact coefficients are peaks, but a
  schedule pays the average of the impact path — two thirds of the peak under
  the square root. Quoting the peak overstates the bill by half, which on this
  run is 415 basis points.
- **Scheduling under one impact law and charging under another.** Almgren-Chriss
  has a closed form only for linear impact; the cost here comes from the
  square-root law, which has the better evidence behind it. The linear
  coefficient is fitted to agree with the square-root law at the order being
  scheduled, and a test asserts that the risk-neutral trajectory then costs
  exactly what the law charges.
- **Reading a tail number without its sample.** A 99% expected shortfall over
  four years is an average of about ten observations. The count is printed next
  to the estimate rather than left in a footnote.
- **Funding overnight.** A position held for four years is financed at the
  four-year point of the curve, not at the front of it.

## Running it differently

The conclusion is not a property of the seed, and the way to see that is to
change it:

```console
$ paper-to-live run --seed 7      # a different simulated market
$ paper-to-live run --notional 5000000   # a tenth of the size
$ paper-to-live run --json        # every figure, for a spreadsheet
```

At a tenth of the capital the annual execution drag falls from 207 basis
points to 66 — a third, not a tenth, because the impact law is a square root —
and what survives rises from 0.35 to 0.48. The deflated Sharpe ratio does not
move at all, since the size of the book has nothing to do with the size of the
search. That is the point: execution and financing are real costs and they are
not the reason this strategy fails.

A test sweeps the seeds and asserts that no draw produces a deflated Sharpe
ratio a reader would fund. Another asserts that 0.95 is a threshold this setup
*could* reach, since an assertion no input can violate tests nothing.

## What is checked, and against what

Everything above is this repository's own output, which is the easiest kind of
number to produce and the hardest to believe. So here is what each line was
checked against, before the install line. Every figure is produced by
`paper-to-live run --json`, which CI runs against the built wheel and which
this repository's suite reads back, so a figure that moves fails on the commit
that moved it:

| Check | Result |
| --- | --- |
| The search run against a market with no exploitable structure | winner's paper Sharpe 0.82, deflated to 0.70; under 0.95 at every seed swept |
| 0.95 shown to be reachable at all, so the row above is evidence | a 0.10 daily Sharpe over the same 1008 days clears it; a quarter of that edge does not |
| The erosion column, as an identity rather than an arrangement | 0.8226 less 0.2039 less 0.2732 is 0.3455, residue 0.0 |
| 322 crossover rules, counted as independent trials | 35.0 effective, by the eigenvalue method |
| Recovered positions against the return series they came from | worst error exactly 0.0 over 1008 days, 0 of them ambiguous |
| The bootstrapped curve repricing the quotes it was built from | 5.6e-17 worst error, 4 instruments |
| Published impact coefficients used as averages rather than as peaks | 415 bps against the 207 bps actually charged |
| The financing haircut by three routes, one of them another package | the hurdle, the drop and holdout.financing_impact agree to 3e-16 |

**The first row is the one the project exists for.** The generator's drift term
is zero, so the simulated market has nothing in it to find and whatever wins a
search over it won by luck. That makes the deflated Sharpe ratio a measurement
against a *known answer*: the true Sharpe ratio is zero, and the honest report
of a 0.82 winner is a coin flip's worth of evidence that it is not worthless.
Coming back with 0.70 is the library being right rather than the library
producing a number. A test sweeps six seeds and asserts the figure never
reaches 0.95 at any of them, so the conclusion is not a property of the seed
this page happens to print.

**The second row guards the first.** An assertion no input can violate tests
nothing, so 0.95 has to be shown attainable on the same sample length and the
same trial dispersion — otherwise "never above 0.95" is a statement about the
threshold rather than about the market.

**The last row checks this repository against a different one.** The funding
stage reports the Sharpe ratio before financing, the ratio after it, and the
hurdle; the first two differ by the third, because the hurdle is
`zero / annual_volatility` and the drop is `daily * sqrt(252) / sd`, which is
the same number reached two ways inside one dataclass. Nothing asserted that
they agreed. `holdout.financing_impact` is a third route from outside this
package entirely, and its closed form `rate / volatility` is a fourth with a
residual that has to be zero because the rate is constant over the horizon. All
of them land on 0.22417514. An agreement with an outside implementation is
worth more than any assertion this repository could make on its own, which is
also why it is checked at three valuation dates rather than at the one printed
above.

That comparison also settled a convention the module had only argued for in a
comment. The stage reads a continuously compounded zero rate and charges
`zero / 252` a day, where subtracting from an arithmetic return wants
`expm1(zero / 252)`. The looseness is **1.3e-05 of annualised Sharpe ratio
against a haircut of 0.224** — four orders below the thing being corrected, so
the convention is justified by a measurement rather than by the argument.

**The third and fifth rows are exact zeros, not small numbers.** The erosion
column either adds up or the four figures printed above are not a decomposition
of anything. The recovered holdings either reproduce the series they were
derived from or every cost below them was computed for a strategy nobody ran —
which is why that check raises rather than warning.

The repricing error is quoted as a bound rather than as digits, deliberately.
The last bits a root-found quantity lands on are not reproducible across
interpreters — the same figure in `tenor` comes back at -8.3e-14 on CPython
3.12 and +1.3e-13 on 3.11 — so ten significant places would be a number that
happens to be true where it was measured. The bound is the claim.

```bash
paper-to-live run --json     # every figure above, as a payload
```

Behind them: 100 tests on Python 3.10 through 3.13, run against the four
libraries built from their default branches at job time.

## Installing

The four libraries are not on a package index yet, so until they are, install
them from source first:

```console
$ pip install git+https://github.com/DaniyalMlk/holdout.git \
              git+https://github.com/DaniyalMlk/slippage.git \
              git+https://github.com/DaniyalMlk/shortfall.git \
              git+https://github.com/DaniyalMlk/tenor.git
$ pip install -e .
```

CI does the same thing, building each library from its default branch at job
time with no cache: this repository exists to show that the four fit together,
and a stale wheel would hide the day they stop.

When they are released, that first command becomes `pip install paper-to-live`
and nothing else changes. The declared requirements are already the bounded
ranges a published distribution has to carry — a `git+https` direct reference
is refused on upload, so it cannot be what the metadata says — which means the
metadata here is correct and currently unsatisfiable.

That is a trap worth closing rather than remembering, so the release workflow
closes it. Its first job asks the index whether every declared requirement can
actually be resolved, with no wheelhouse on the path, which is the resolve
`pip install paper-to-live` performs. A version tag pushed before the four
libraries exist fails there instead of publishing something nobody can
install — and a published version can never be replaced. The job turns green on
its own on the day they are released, with nothing edited.

## Layout

| Module | Stage |
| --- | --- |
| `selection.py` | The candidate set and the deflation of its winner |
| `execution.py` | Parent orders, impact, and the net return series |
| `risk.py` | Value at risk, expected shortfall, drawdown |
| `funding.py` | The discount curve and the financing hurdle |
| `pipeline.py` | The four in order, and the erosion between them |
| `report.py` | The table above |

Each stage is a pure function of the settings and the stage before it, so any
one of them can be run alone.

See [ROADMAP.md](ROADMAP.md).
