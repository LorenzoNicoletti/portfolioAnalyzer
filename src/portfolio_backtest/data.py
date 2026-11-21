"""Loading the monthly EUR price series.

The data file is a Curvo Backtest export (not included in the repository, see data/README.md):
an Excel workbook with a sheet "Prices EUR" where row 2 holds the ISINs from column B on,
column A holds the months from row 3 on, and the cells hold the monthly values in EUR.

The file is looked up in this order: an explicit path, the ``PORTFOLIO_BACKTEST_DATA``
environment variable, then ``data/Curvo_ETF_Monthly_EUR.xlsx`` in the repository.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import pandas as pd

from .etfs import CODES, ETFS

DATA_ENV_VAR = "PORTFOLIO_BACKTEST_DATA"
DEFAULT_DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "Curvo_ETF_Monthly_EUR.xlsx"
SHEET = "Prices EUR"


def data_path(path: str | Path | None = None) -> Path:
    if path is None:
        path = os.environ.get(DATA_ENV_VAR) or DEFAULT_DATA_FILE
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Price data not found at {path}. Put the Curvo export there, pass --data, "
            f"or set {DATA_ENV_VAR}. See data/README.md."
        )
    return path


@lru_cache(maxsize=4)
def _load(path: Path) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=SHEET, header=None)
    isins = raw.iloc[1, 1:].tolist()
    df = raw.iloc[2:, :].copy()
    df.columns = ["Month"] + isins
    df["Month"] = pd.to_datetime(df["Month"])
    df = df.set_index("Month").astype(float)
    df = df.rename(columns={e.isin: e.code for e in ETFS.values()})
    missing = [c for c in CODES if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name} has no series for: {', '.join(missing)}")
    return df[list(CODES)]


def load_prices(path: str | Path | None = None) -> pd.DataFrame:
    """All monthly EUR series: columns = ETF codes, index = month start. Read once per file, then cached."""
    return _load(data_path(path))


def window(prices: pd.DataFrame, start: str, end: str | None = None) -> pd.DataFrame:
    """Rows from month ``start`` to month ``end`` (both "YYYY-MM", inclusive)."""
    out = prices.loc[pd.Timestamp(start + "-01"):]
    if end:
        out = out.loc[: pd.Timestamp(end + "-01")]
    if len(out) < 2:
        raise ValueError(f"Less than two months of data between {start} and {end or 'the end'}.")
    return out
