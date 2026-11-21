# Price data

This folder is git-ignored except for this file. The price data comes from [Curvo Backtest](https://curvo.eu/backtest) and is not redistributed here.

## Expected file

`data/Curvo_ETF_Monthly_EUR.xlsx`, an Excel workbook with a sheet named **`Prices EUR`**:

| | A | B | C | … |
|---|---|---|---|---|
| 1 | (any) | (any, e.g. fund names) | | |
| 2 | (any) | ISIN | ISIN | … |
| 3+ | month (date) | value in EUR | value in EUR | … |

- One row per month, oldest first.
- One column per ETF, identified by the ISIN in row 2.
- Empty cells are allowed before a fund's series starts.
- The file must contain a column for every ISIN listed in `src/portfolio_backtest/etfs.py`.

## Using a file somewhere else

The file can live anywhere. Point the code to it in one of these ways:

- pass it on the command line: `portfolio-backtest --data path/to/file.xlsx`
- set an environment variable: `PORTFOLIO_BACKTEST_DATA=path/to/file.xlsx`
- in Python, call `load_prices("path/to/file.xlsx")` and pass the result as `prices=` to `backtest` or `perform_backtest`
