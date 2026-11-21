"""The data workbook: monthly EUR price series from Curvo Backtest, plus one row of info per ETF.

The workbook is created and extended from Curvo with ``portfolio data update`` / ``portfolio data add``
(see curvo.py) and is git-ignored. Layout (see "The data workbook" in README.md):

- sheet ``Prices EUR``: row 1 tickers, row 2 ISINs (from column B on), months in column A from row 3 on.
- sheet ``Fund info``:  one row per ETF (Ticker, Fund, ISIN, Tickers, ...), then a blank row and notes.

Loading the workbook registers every ETF in it (etfs.register), so the tickers of added ETFs work everywhere.
The file is looked up in this order: an explicit path, the ``PORTFOLIO_BACKTEST_DATA``
environment variable, then ``data/Curvo_ETF_Monthly_EUR.xlsx`` in the repository.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

import pandas as pd

from . import etfs as registry
from .etfs import ETF, register, ticker_for_isin

DATA_ENV_VAR = "PORTFOLIO_BACKTEST_DATA"
DEFAULT_DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "Curvo_ETF_Monthly_EUR.xlsx"
PRICES_SHEET = "Prices EUR"
INFO_SHEET = "Fund info"
INFO_COLUMNS = ["Ticker", "Fund", "ISIN", "Tickers", "Tracked index", "TER %", "Fund inception",
                "Series start", "Series end", "Dividends", "Curvo Backtest link", "Retrieved"]


def data_path(path: str | Path | None = None, must_exist: bool = True) -> Path:
    if path is None:
        path = os.environ.get(DATA_ENV_VAR) or DEFAULT_DATA_FILE
    path = Path(path)
    if must_exist and not path.is_file():
        raise FileNotFoundError(
            f"Price data not found at {path}. Create it from Curvo with: portfolio data update "
            f"(or pass --data / set {DATA_ENV_VAR}). See README.md."
        )
    return path


# ------------------------------------------------------------------ reading --
def read_workbook(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(prices, info) as stored: prices has one column per ISIN, info is indexed by ISIN."""
    sheets = pd.read_excel(path, sheet_name=None, header=None)
    raw = sheets[PRICES_SHEET]
    isins = [str(i).strip().upper() for i in raw.iloc[1, 1:]]
    prices = raw.iloc[2:, :].copy()
    prices.columns = ["Month"] + isins
    prices["Month"] = pd.to_datetime(prices["Month"])
    prices = prices.set_index("Month").astype(float)

    info = pd.DataFrame(columns=INFO_COLUMNS).set_index("ISIN")
    if INFO_SHEET in sheets:
        raw = sheets[INFO_SHEET]
        header = [str(h) for h in raw.iloc[0]]
        rows = []
        for _, row in raw.iloc[1:].iterrows():
            if row.isna().all():
                break  # the notes start after the first blank row
            rows.append(row.tolist())
        df = pd.DataFrame(rows, columns=header).dropna(axis=1, how="all")
        if "ISIN" in df:
            df["ISIN"] = df["ISIN"].astype(str).str.strip().str.upper()
            info = df.set_index("ISIN")
    return prices, info


def _etf_for(isin: str, info: pd.DataFrame) -> ETF:
    """The ETF of a price column: the known one for this ISIN, else Ticker and Fund from the info sheet.

    Without a Ticker cell (older workbooks), the first of the fund's Curvo tickers is used, else the ISIN.
    """
    known = ticker_for_isin(isin)
    if known:
        return registry.ETFS[known]
    row = info.loc[isin] if isin in info.index else pd.Series(dtype=object)
    curvo_tickers = [t.strip().upper() for t in str(row.get("Tickers") or "").split(",") if t.strip()]
    ticker = str(row.get("Ticker") or "").strip().upper() or (curvo_tickers[0] if curvo_tickers else isin)
    return ETF(ticker, isin, str(row.get("Fund") or "").strip() or isin)


@lru_cache(maxsize=4)
def _load(path: Path) -> pd.DataFrame:
    prices, info = read_workbook(path)
    prices.columns = [register(_etf_for(isin, info)).ticker for isin in prices.columns]
    return prices


def load_prices(path: str | Path | None = None) -> pd.DataFrame:
    """All monthly EUR series: columns = tickers, index = month start. Read once per file, then cached.

    Also registers every ETF in the workbook, so their tickers can be used in allocations.
    """
    return _load(data_path(path))


def clear_cache() -> None:
    """Forget loaded workbooks, e.g. after the file was updated."""
    _load.cache_clear()


# ------------------------------------------------------------------ writing --
def write_workbook(path: Path, prices: pd.DataFrame, info: pd.DataFrame, notes: Iterable[str] = ()) -> None:
    """Write (prices by ISIN, info by ISIN) in the layout read_workbook expects."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    bold = Font(bold=True)
    info = info.reindex(prices.columns)
    tickers = [str(t) if pd.notna(t) else isin for isin, t in zip(prices.columns, info.get("Ticker", info.index))]

    wb = Workbook()
    ws = wb.active
    ws.title = PRICES_SHEET
    ws.append(["Ticker"] + tickers)
    ws.append(["ISIN"] + list(prices.columns))
    for month, row in prices.sort_index().iterrows():
        ws.append([month.to_pydatetime()] + [None if pd.isna(v) else float(v) for v in row])
    for cell in ws["A"][2:]:
        cell.number_format = "mmm yyyy"
    for cell in list(ws[1]) + list(ws[2]):
        cell.font = bold
    ws.column_dimensions["A"].width = 11
    ws.freeze_panes = "B3"

    ws = wb.create_sheet(INFO_SHEET)
    extra = [c for c in info.columns if c not in INFO_COLUMNS]  # keep any columns the user added
    header = INFO_COLUMNS + extra
    ws.append(header)
    for isin, row in info.iterrows():
        values = {**row.to_dict(), "ISIN": isin}
        ws.append([None if pd.isna(values.get(h)) else values.get(h) for h in header])
    for cell in ws[1]:
        cell.font = bold
    notes = list(notes)
    if notes:
        ws.append([])
        ws.append(["Notes"])
        ws.cell(ws.max_row, 1).font = bold
        for line in notes:
            ws.append([line])

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    clear_cache()


# ------------------------------------------------------------------ windows --
def common_period(prices: pd.DataFrame, tickers: Iterable[str]) -> tuple[str, str]:
    """First and last month ("YYYY-MM") in which every ETF in tickers has data."""
    tickers = list(dict.fromkeys(tickers))
    full = prices[tickers].dropna()
    if full.empty:
        raise ValueError(f"No month in which all of {', '.join(tickers)} have data.")
    return f"{full.index[0]:%Y-%m}", f"{full.index[-1]:%Y-%m}"


def common_start(prices: pd.DataFrame, tickers: Iterable[str]) -> str:
    """First month ("YYYY-MM") in which every ETF in tickers has data."""
    return common_period(prices, tickers)[0]


def window(prices: pd.DataFrame, start: str, end: str | None = None) -> pd.DataFrame:
    """Rows from month ``start`` to month ``end`` (both "YYYY-MM", inclusive)."""
    out = prices.loc[pd.Timestamp(start + "-01"):]
    if end:
        out = out.loc[: pd.Timestamp(end + "-01")]
    if len(out) < 2:
        raise ValueError(f"Less than two months of data between {start} and {end or 'the end'}.")
    return out
