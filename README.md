# portfolio-backtest

Backtest fixed-weight ETF portfolios on monthly EUR data, and explore thousands of allocations at once with an interactive Sobol study. Everything goes through one class, `PortfolioAnalyzer`, or the `portfolio` command.

- **Vectorised engine.** Backtests thousands of portfolios in one pass, with no Python loop over portfolios or months. The results match a month-by-month simulation exactly; a test checks this.
- **Rebalancing:** none, monthly, quarterly, semiannual or annual.
- **Metrics:** final value, CAGR, annualised volatility and maximum drawdown.
- **Sobol study.** Samples allocations evenly over every possible mix of the chosen ETFs and plots them on a volatility vs CAGR chart. You can filter the points by weight per ETF, click a point to see its allocation, and compare any mix you type in.
- **Data straight from Curvo.** Downloads the monthly EUR series from [Curvo Backtest](https://curvo.eu/backtest) through its MCP server and keeps them in an Excel workbook. Add any ETF Curvo knows by ticker or ISIN. ETFs are identified by their ticker everywhere: in allocations, in the Sobol study, in filters and in the charts.

## Install

Python 3.10 or newer.

```bash
git clone https://github.com/LorenzoNicoletti/portfolioAnalyzer.git
cd portfolioAnalyzer
pip install -e .            # add ".[qt]" for the "Custom mix" side panel, ".[dev]" for the tests
```

## Quick start

The easiest way is [main.py](main.py): edit the settings at the top (allocation, amount, period, rebalancing, ETFs to add, Sobol ETFs and filters), then run it:

```bash
python main.py              # or Run / F5 in VS Code
```

It downloads the data on the first run, prints the ETF list, shows the backtest (close the chart to continue) and opens the Sobol study.

The same with the command line:

```bash
portfolio data update       # first run: download the data from Curvo
portfolio backtest          # backtest the basis allocation
portfolio sobol             # interactive Sobol study
```

Or from Python:

```python
from portfolio_backtest import PortfolioAnalyzer

pa = PortfolioAnalyzer()                    # basis allocation, 10,000 EUR, annual rebalancing
pa.update_data()                            # create / refresh the data workbook from Curvo
pa.add_etfs("EUNL", "IE00B5BMR087=SXR8")    # add ETFs by ticker or ISIN (=TICKER picks the fund's ticker)
pa.list_etfs()                              # the ETFs in the workbook (a DataFrame)
pa.backtest()                               # table + chart of the allocation and each ETF alone
pa.sobol(["UETW", "SXRQ", "PPFB"])          # interactive volatility vs CAGR cloud
```

## PortfolioAnalyzer

```python
PortfolioAnalyzer(alloc=None, invest=10_000, start=None, end=None, rebalance="annual", data=None)
```

| Setting | Meaning |
|---|---|
| `alloc` | `{ticker or ISIN: %}`, sums to 100. Default: the basis allocation AEME 13 / UETW 25 / VUAA 10 / SXRQ 20 / PPFB 10 / LYP6 22 (`DEFAULT_ALLOC` in `etfs.py`) |
| `invest` | lump sum in EUR |
| `start`, `end` | `"YYYY-MM"`. Default: the first and last month in which every ETF involved has data |
| `rebalance` | `none`, `monthly`, `quarterly`, `semiannual` or `annual` |
| `data` | path to the data workbook (default `data/Curvo_ETF_Monthly_EUR.xlsx`) |

The settings are plain attributes, so you can change them between calls, e.g. `pa.alloc = {"UETW": 60, "SXRQ": 40}` or `pa.rebalance = "quarterly"`.

| Method | What it does | Returns |
|---|---|---|
| `update_data()` | creates the workbook with the six built-in ETFs, or downloads every series again (new months) | ISINs fetched |
| `add_etfs(*etfs)` | adds ETFs from Curvo by ticker (`"EUNL"`) or ISIN (`"IE00B5BMR087"` gets the fund's first ticker; `"IE00B5BMR087=SXR8"` picks one) | `[(ticker, ISIN)]` |
| `list_etfs()` | the ETFs in the workbook: ticker, ISIN, first/last month, fund | `DataFrame` |
| `backtest(report=True, plot=True, show_single=True)` | prints the table and plots the value over time | `BacktestResults`: row 0 is the portfolio, row 1 + j the j-th held ETF alone |
| `sobol(etfs=..., n_samples=8192, seed=42, filters=None, plot=True)` | Sobol study over the mixes of `etfs`; the allocation is the white diamond. `filters`: `{ticker: (min %, max %)}` active when the chart opens | `SobolStudy` |

The engine is also available directly, to backtest many portfolios at once:

```python
from portfolio_backtest import perform_backtest

many = perform_backtest(10_000, ["UETW", "SXRQ"], [[60, 40], [80, 20], [100, 0]])  # one row per portfolio
many.cagr, many.volatility, many.max_drawdown
```

## Command line

One command, `portfolio`, with one subcommand per method:

```bash
portfolio data update                                       # create the workbook, or download every series again
portfolio data add EUNL IE00B5BMR087=SXR8                   # add ETFs by ticker or ISIN (ISIN=TICKER picks the ticker)
portfolio data list                                         # the ETFs in the workbook

portfolio backtest                                          # the basis allocation, 10,000 EUR, annual rebalancing
portfolio backtest --alloc UETW=50 AEME=10 SXRQ=30 PPFB=10
portfolio backtest --invest 25000 --rebalance none --start 2010-01 --end 2020-12
portfolio backtest --no-plot                                # table only

portfolio sobol                                             # 8192 mixes of AEME, UETW, SXRQ, PPFB, LYP6
portfolio sobol --etfs UETW SXRQ PPFB --samples 4096
portfolio sobol --etfs EUNL SXR8 SXRQ PPFB                  # added ETFs work too
portfolio sobol --filter PPFB=10-30 --rebalance quarterly
portfolio sobol --alloc UETW=50 SXRQ=40 PPFB=10             # the white reference diamond
```

`--alloc`, `--invest`, `--start`, `--end`, `--rebalance` and `--data` work for both `backtest` and `sobol`. `python -m portfolio_backtest` is the same as `portfolio`.

![Sobol study](docs/sobol.png)

## Data

The price data is **not** in the repository (the `data/` folder is git-ignored), because Curvo's data is not ours to redistribute. You download it yourself with `portfolio data update` / `pa.update_data()`. This needs internet access, but no account and no API key. The data comes from Curvo's public MCP server (`https://curvo.eu/backtest/mcp`), which is called with the `mcp` Python package; `pip install` installs it.

Each added ETF becomes a new column in the workbook's `Prices EUR` sheet and a new row in `Fund info`. From then on its ticker works everywhere: in `alloc`, in the Sobol `etfs` and in `filters`. If a ticker is ambiguous or unknown on Curvo, you get the list of candidates; use the ISIN instead.

### The data workbook

`data/Curvo_ETF_Monthly_EUR.xlsx` has two sheets.

**`Prices EUR`**: one column per ETF, one row per month (oldest first).

| | A | B | C | … |
|---|---|---|---|---|
| 1 | Ticker | ticker | ticker | … |
| 2 | ISIN | ISIN | ISIN | … |
| 3+ | month (date) | value in EUR | value in EUR | … |

- Columns are identified by the ISIN in row 2.
- Cells are empty before a fund's series starts.

**`Fund info`**: one row per ETF with Ticker, Fund, ISIN, Tickers (all the fund's tickers on Curvo), Tracked index, TER %, Fund inception, Series start, Series end, Dividends, Curvo Backtest link and Retrieved, then a blank row and notes.

- The **Ticker** is what you use in allocations, `etfs` and `filters`, and what the charts show. The six built-in ETFs always keep theirs (AEME, UETW, VUAA, SXRQ, PPFB, LYP6).
- Columns you add yourself are kept when the workbook is updated.
- Older workbooks with a Code column instead of Ticker still load; ETFs that aren't built in then get the first of their Curvo tickers, and the next update rewrites the workbook with a Ticker column.

### Using a file somewhere else

The workbook can live anywhere. Point the code to it in one of these ways:

- `PortfolioAnalyzer(data="path/to/file.xlsx")`, or `--data path/to/file.xlsx` on the command line
- set an environment variable: `PORTFOLIO_BACKTEST_DATA=path/to/file.xlsx`

## ETFs

| Ticker | ETF | ISIN |
|---|---|---|
| AEME | Amundi Core MSCI Emerging Markets Acc | LU1437017350 |
| UETW | UBS Core MSCI World USD acc | IE00BD4TXV59 |
| VUAA | Vanguard S&P 500 (USD) Acc | IE00BFMXXD54 |
| SXRQ | iShares Euro Govt Bond 7-10yr (Acc) | IE00B3VTN290 |
| PPFB | iShares Physical Gold ETC | IE00B4ND3602 |
| LYP6 | Amundi Stoxx Europe 600 Acc | LU0908500753 |

These six are built in. Anywhere a ticker is accepted, the ISIN works too. To add an ETF, use `add_etfs` / `portfolio data add`; its ticker is stored in the workbook, so no code change is needed.

## How it works

Between two rebalancing dates, each portfolio is simply bought and held. If s(t) is the last rebalancing month before t, the value at month t is:

```
V(t) = V(s(t)) · Σᵢ wᵢ · Pᵢ(t) / Pᵢ(s(t))
```

At each rebalancing date, the value is the running product of the growth over each finished period. All of this is matrix operations over (months × ETFs) and (portfolios × ETFs).

The Sobol allocations work like this: take a scrambled Sobol point u in [0,1)ᵈ, compute e = −ln(1−u), and set w = 100·e/Σe. This spreads the points evenly over every possible mix.

## Project layout

```
main.py          main script: settings at the top, then data -> backtest -> sobol
src/portfolio_backtest/
  analyzer.py    PortfolioAnalyzer: the one class you use (data, backtest, sobol)
  cli.py         the portfolio command (one subcommand per method)
  etfs.py        ETF registry (built-in + added), default allocation, allocation validation
  data.py        reading and writing the data workbook
  curvo.py       Curvo MCP client: add ETFs, refresh series
  engine.py      vectorised backtest and metrics
  plotting.py    backtest chart and style helpers
  sobol/
    study.py     Sobol sampling and batch backtest
    explorer.py  interactive chart (filters, click labels, custom-mix panel)
tests/           pytest; uses synthetic prices and a fake Curvo client, so no data file or network is needed
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## Disclaimer

The data is Curvo's simulation from each index minus the fund's TER, not actual fund prices. Past performance does not guarantee future results. This is a personal analysis tool, not investment advice.
