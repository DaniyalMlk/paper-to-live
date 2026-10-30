# paper-to-live

A backtested strategy, walked from its paper Sharpe ratio to the number a desk
would actually underwrite.

```console
$ pip install paper-to-live
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

**[daniyalmlk.github.io/paper-to-live](https://daniyalmlk.github.io/paper-to-live/)**
— the same run with the erosion column drawn rather than tabulated, generated
when the page was built. Every figure on it comes from the payload below.

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

Behind them: 120 tests on Python 3.10 through 3.13, run against the four
libraries built from their default branches at job time.

## Known gaps

Every deduction in this report is one the surviving Sharpe ratio has already
paid. What follows is what it has not, and the list is worth reading in one
particular way: every omission points the same direction. Each of these would
take the surviving figure down further, none of them would put any of it back.
`tests/test_known_gaps.py` pairs each line with a check that it is still
missing, because a sibling repository's gap list turned out to contain two
lines describing things that had been built months earlier, and a list nobody
rechecks is read as current anyway.

- **One instrument.** One simulated price series, one position in it. A real
  book holds many names at once, and what that changes is not the cost of any
  single trade but the diversification that would have been earned alongside
  it — so a multi-asset version of this strategy would have a better Sharpe
  ratio before costs and a worse one per unit of capacity.
- **The holding is one of three values.** Short, flat or long, at full size.
  No volatility targeting, no scaling into a signal, no risk budget. The
  expected shortfall and the drawdown reported are therefore the instrument's
  own, not a risk-managed book's, and a desk that would have cut the position
  in the drawdown would have had a smaller loss and a smaller return.
- **No borrow cost, and no borrow at all.** The short days are free and always
  available. A hard-to-borrow name costs a fee that scales with how crowded
  the short is, and the days it cannot be located at all are days the
  strategy did not get the position it was backtested as holding — both of
  which take the surviving figure down, and the second of which is not a cost
  but a different strategy.
- **Financing is charged on the capital, every day.** This one is a choice
  rather than an omission, and it is worth being explicit: the zero rate is
  subtracted from every day's return whatever the book was holding. A long
  funded with borrowed cash pays it; a short earns something on its proceeds
  and a flat day earns it on cash. The convention here is the conservative
  reading — that the capital has a cost whether or not it is deployed — and
  `run_funding` is handed the return series and nothing else, so it could not
  do otherwise.
- **One screen, read at one horizon.** Four quoted instruments, one valuation
  date, and the zero rate read at the length of the backtest. The curve does
  not move over the hold, so a strategy run across a tightening is funded
  throughout at whatever the curve said on day one.
- **No capacity.** The impact law charges each order for the volume it takes,
  but the strategy's own prints never move the series the next rule is fitted
  to. So doubling the notional doubles the cost and leaves the signal
  untouched, when in a real market the signal is partly what the trading has
  already arbitraged away.
- **No tax.** Nothing is withheld on the carry and nothing is paid on the
  gain. For a strategy turning over forty-two times a year the difference
  between a long-term and a short-term rate is not a rounding adjustment.
- **No dividends and no corporate actions.** The simulated series is a price,
  so a short pays no dividend and a long receives none, and no split, spin-off
  or index reconstitution interrupts the position. Each of those is a day the
  backtested holding and the holdable holding differ.
- **Execution is a cost law, not a market.** The square-root impact law and
  the optimal schedule behind it are a model of average cost against
  participation. There is no latency, no queue position, no venue choice, no
  spread to cross and no adverse selection against a resting order — so the
  cost figure is the part of execution that can be written down, not all of
  it.
- **One currency.** Every amount is in the same money, so there is no hedge
  to pay for and no basis to carry. A strategy funded in one currency and
  traded in another pays for the mismatch, and the cost of doing so moves
  around rather more than the financing rate does.
- **No regime.** The market is one simulation with one set of parameters and,
  by default, no exploitable drift at all. That is deliberate — the point of
  the default is that the winner's performance is entirely selection — but it
  means nothing here says how any of these numbers behave when volatility
  trebles, which is the condition under which every one of them gets worse at
  once.

## Installing

```console
$ pip install paper-to-live
```

That one command brings the four libraries with it. Three of them are
importable under a shorter name than the one the index serves them by, because
the short names belong to unrelated projects:

| requirement | imports as |
| --- | --- |
| `holdout-backtest` | `holdout` |
| `slippage-tca` | `slippage` |
| `shortfall` | `shortfall` |
| `tenor-curves` | `tenor` |

CI does not install them that way. It builds each from its default branch at
job time with no cache, because this repository exists to show that the four
fit together, and a released wheel would hide the day they stop fitting by
pinning them to the last version that worked.

**The release workflow refuses to publish something nobody can install.** Its
first job asks the index whether every declared requirement resolves, with no
wheelhouse on the path, which is exactly the resolve `pip install
paper-to-live` performs for a stranger. The declared requirements are bounded
ranges rather than `git+https` direct references — those are refused on upload,
so they could never have been what the metadata said — which meant that for as
long as the libraries were unpublished, the metadata here was correct and
unsatisfiable. A version tag pushed in that window would have failed at that
job rather than publishing a package that installs and then cannot resolve, and
a published version can never be replaced. The job went green on its own on the
day the libraries were released, with nothing here edited to make it.

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
