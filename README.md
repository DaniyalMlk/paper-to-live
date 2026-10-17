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
