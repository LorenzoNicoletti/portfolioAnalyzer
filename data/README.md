# Price data

This folder is git-ignored except for this file. The price data comes from [Curvo Backtest](https://curvo.eu/backtest) and is not redistributed here. Create it yourself:

```bash
portfolio-data update          # creates Curvo_ETF_Monthly_EUR.xlsx with the six built-in ETFs
portfolio-data add EUNL        # adds more ETFs by ticker or ISIN (optionally TICKER=CODE)
```

## The workbook

`data/Curvo_ETF_Monthly_EUR.xlsx` has two sheets.

**`Prices EUR`**: one column per ETF, one row per month (oldest first).

| | A | B | C | … |
|---|---|---|---|---|
| 1 | Code | ETF code | ETF code | … |
| 2 | ISIN | ISIN | ISIN | … |
| 3+ | month (date) | value in EUR | value in EUR | … |

- Columns are identified by the ISIN in row 2.
- Cells are empty before a fund's series starts.

**`Fund info`**: one row per ETF with Code, Fund, ISIN, Tickers, Tracked index, TER %, Fund inception, Series start, Series end, Dividends, Curvo Backtest link and Retrieved, then a blank row and notes.

- The **Code** is what you type in `--alloc`, `--etfs`, `--mix` and `--filter`. The six built-in ETFs always keep their codes (EM, WORLD, SP500, BONDS, GOLD, EUROPE).
- Columns you add yourself are kept when the workbook is updated.

Older workbooks without a Code column still load; ETFs that aren't built in then use their ISIN as the code.

## Using a file somewhere else

The file can live anywhere. Point the code to it in one of these ways:

- pass it on the command line: `--data path/to/file.xlsx` (all three commands)
- set an environment variable: `PORTFOLIO_BACKTEST_DATA=path/to/file.xlsx`
- in Python, call `load_prices("path/to/file.xlsx")` and pass the result as `prices=` to `backtest` or `perform_backtest`
