# portfolio-backtest

Backtest fixed-weight ETF portfolios on monthly EUR data, and explore thousands of allocations at once with an interactive Sobol study.

- **Vectorised engine.** Backtests thousands of portfolios in one pass, with no Python loop over portfolios or months. The results match a month-by-month simulation exactly; a test checks this.
- **Rebalancing:** none, monthly, quarterly, semiannual or annual.
- **Metrics:** final value, CAGR, annualised volatility and maximum drawdown.
- **Sobol study.** Samples allocations evenly over every possible mix of the chosen ETFs and plots them on a volatility vs CAGR chart. You can filter the points by weight per ETF, click a point to see its allocation, and compare any mix you type in.

## Install

Python 3.10 or newer.

```bash
git clone https://github.com/LorenzoNicoletti/portfolioAnalyzer.git
cd portfolioAnalyzer
pip install -e .            # add ".[qt]" for the "Custom mix" side panel, ".[dev]" for the tests
```

## Data

The price data is **not** in the repository. The code expects a [Curvo Backtest](https://curvo.eu/backtest) export at `data/Curvo_ETF_Monthly_EUR.xlsx`. [data/README.md](data/README.md) describes the format and where else the file can live.

## Usage

### Backtest one portfolio

```bash
portfolio-backtest                                         # WORLD 60 / BONDS 40, 10,000 EUR, annual rebalancing
portfolio-backtest --alloc WORLD=50 EM=10 BONDS=30 GOLD=10
portfolio-backtest --invest 25000 --rebalance none --start 2010-01 --end 2020-12
portfolio-backtest --no-plot                               # table only
```

This prints a table for the portfolio and each held ETF alone, then plots the value over time.

### Sobol study

```bash
portfolio-sobol                                            # 8192 mixes of EM, WORLD, BONDS, GOLD, EUROPE
portfolio-sobol --etfs WORLD BONDS GOLD --samples 4096
portfolio-sobol --filter GOLD=10-30 --rebalance quarterly
portfolio-sobol --mix WORLD=50 BONDS=40 GOLD=10            # the white reference star
```

![Sobol study](docs/sobol.png)

### From Python

```python
from portfolio_backtest import backtest, perform_backtest

r = backtest(10_000, {"WORLD": 50, "BONDS": 40, "GOLD": 10}, rebalance="annual")
print(r.cagr, r.volatility, r.max_drawdown)
r.values.plot()

# many portfolios at once: one row per portfolio, columns in the order of the ETF list
many = perform_backtest(10_000, ["WORLD", "BONDS"], [[60, 40], [80, 20], [100, 0]])
many.cagr, many.volatility
```

## ETFs

| Code | ETF | ISIN |
|---|---|---|
| EM | Amundi Core MSCI Emerging Markets Acc | LU1437017350 |
| WORLD | UBS Core MSCI World USD acc | IE00BD4TXV59 |
| SP500 | Vanguard S&P 500 (USD) Acc | IE00BFMXXD54 |
| BONDS | iShares Euro Govt Bond 7-10yr (Acc) | IE00B3VTN290 |
| GOLD | iShares Physical Gold ETC | IE00B4ND3602 |
| EUROPE | Amundi Stoxx Europe 600 Acc | LU0908500753 |

Anywhere a code is accepted, the ISIN works too. To add an ETF, add an entry to `ETFS` in `src/portfolio_backtest/etfs.py` and its series to the data file.

## How it works

Between two rebalancing dates, each portfolio is simply bought and held. If s(t) is the last rebalancing month before t, the value at month t is:

```
V(t) = V(s(t)) · Σᵢ wᵢ · Pᵢ(t) / Pᵢ(s(t))
```

At each rebalancing date, the value is the running product of the growth over each finished period. All of this is matrix operations over (months × ETFs) and (portfolios × ETFs).

The Sobol allocations work like this: take a scrambled Sobol point u in [0,1)ᵈ, compute e = −ln(1−u), and set w = 100·e/Σe. This spreads the points evenly over every possible mix.

## Project layout

```
src/portfolio_backtest/
  etfs.py        ETF list, allocation parsing and validation
  data.py        loading the Curvo workbook
  engine.py      vectorised backtest and metrics
  plotting.py    single-portfolio chart and style helpers
  cli.py         portfolio-backtest command
  sobol/
    study.py     Sobol sampling and batch backtest
    explorer.py  interactive chart (filters, click labels, custom-mix panel)
    cli.py       portfolio-sobol command
tests/           pytest; uses synthetic prices, so no data file is needed
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## License

[MIT](LICENSE)

## Disclaimer

The data is Curvo's simulation from each index minus the fund's TER, not actual fund prices. Past performance does not guarantee future results. This is a personal analysis tool, not investment advice.
