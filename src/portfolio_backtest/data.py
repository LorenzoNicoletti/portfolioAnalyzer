"""The data workbook: monthly EUR price series from Curvo Backtest, plus one row of info per ETF.

The workbook is created and extended from Curvo with the ``portfolio-data`` command (see curvo.py)
and is git-ignored. Layout (see data/README.md):

- sheet ``Prices EUR``: row 1 ETF codes, row 2 ISINs (from column B on), months in column A from row 3 on.
- sheet ``Fund info``:  one row per ETF (Code, Fund, ISIN, Tickers, ...), then a blank row and notes.

Loading the workbook registers every ETF in it (etfs.register), so codes of added ETFs work everywhere.
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
from .etfs import ETF, code_for_isin, register

DATA_ENV_VAR = "PORTFOLIO_BACKTEST_DATA"
DEFAULT_DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "Curvo_ETF_Monthly_EUR.xlsx"
PRICES_SHEET = "Prices EUR"
INFO_SHEET = "Fund info"
INFO_COLUMNS = ["Code", "Fund", "ISIN", "Tickers", "Tracked index", "TER %", "Fund inception",
                "Series start", "Series end", "Dividends", "Curvo Backtest link", "Retrieved"]


def data_path(path: str | Path | None = None, must_exist: bool = True) -> Path:
    if path is None:
        path = os.environ.get(DATA_ENV_VAR) or DEFAULT_DATA_FILE
    path = Path(path)
    if must_exist and not path.is_file():
        raise FileNotFoundError(
            f"Price data not found at {path}. Create it from Curvo with: portfolio-data update "
            f"(or pass --data / set {DATA_ENV_VAR}). See data/README.md."
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
    """The ETF of a price column: the known one for this ISIN, else Code and Fund from the info sheet."""
    known = code_for_isin(isin)
    if known:
        return registry.ETFS[known]
    row = info.loc[isin] if isin in info.index else pd.Series(dtype=object)
    code = str(row.get("Code") or "").strip().upper() or isin
    name = str(row.get("Fund") or "").strip() or isin
    return ETF(code, isin, name)


@lru_cache(maxsize=4)
def _load(path: Path) -> pd.DataFrame:
    prices, info = read_workbook(path)
    codes = [register(_etf_for(isin, info)).code for isin in prices.columns]
    prices.columns = codes
    return prices


def load_prices(path: str | Path | None = None) -> pd.DataFrame:
    """All monthly EUR series: columns = ETF codes, index = month start. Read once per file, then cached.

    Also registers every ETF in the workbook, so their codes can be used in allocations.
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
    codes = [str(c) if pd.notna(c) else isin for isin, c in zip(prices.columns, info.get("Code", info.index))]

    wb = Workbook()
    ws = wb.active
    ws.title = PRICES_SHEET
    ws.append(["Code"] + codes)
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
def common_start(prices: pd.DataFrame, codes: Iterable[str]) -> str:
    """First month ("YYYY-MM") in which every ETF in codes has data."""
    codes = list(dict.fromkeys(codes))
    full = prices[codes].dropna()
    if full.empty:
        raise ValueError(f"No month in which all of {', '.join(codes)} have data.")
    return f"{full.index[0]:%Y-%m}"


def window(prices: pd.DataFrame, start: str, end: str | None = None) -> pd.DataFrame:
    """Rows from month ``start`` to month ``end`` (both "YYYY-MM", inclusive)."""
    out = prices.loc[pd.Timestamp(start + "-01"):]
    if end:
        out = out.loc[: pd.Timestamp(end + "-01")]
    if len(out) < 2:
        raise ValueError(f"Less than two months of data between {start} and {end or 'the end'}.")
    return out
