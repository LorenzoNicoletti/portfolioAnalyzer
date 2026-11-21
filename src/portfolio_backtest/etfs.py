"""The ETF universe and allocation handling.

Every ETF is identified by its exchange ticker (e.g. ``UETW``): in allocations, in the Sobol study,
in filters and in every chart. An ISIN works as input too. Six ETFs are built in; ETFs added from
Curvo with ``portfolio data add`` are registered from the data workbook when it is loaded (see data.py).

An allocation maps tickers (or ISINs) to percentages that sum to 100, e.g. ``{"UETW": 60, "SXRQ": 40}``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ETF:
    ticker: str
    isin: str
    name: str


BUILTIN_ETFS: tuple[ETF, ...] = (
    ETF("AEME", "LU1437017350", "Amundi MSCI EM"),
    ETF("UETW", "IE00BD4TXV59", "UBS MSCI World"),
    ETF("VUAA", "IE00BFMXXD54", "Vanguard S&P 500"),
    ETF("SXRQ", "IE00B3VTN290", "iShares EUR Govt 7-10yr"),
    ETF("PPFB", "IE00B4ND3602", "iShares Physical Gold"),
    ETF("LYP6", "LU0908500753", "Amundi Stoxx Europe 600"),
)

# All known ETFs by ticker: the built-in ones, plus the ones registered from the data workbook.
ETFS: dict[str, ETF] = {e.ticker: e for e in BUILTIN_ETFS}
_BY_ISIN = {e.isin: e.ticker for e in ETFS.values()}

# Default (basis) allocation, used when no other allocation is given.
DEFAULT_ALLOC: dict[str, float] = {"AEME": 13, "UETW": 25, "VUAA": 10, "SXRQ": 20, "PPFB": 10, "LYP6": 22}


def register(etf: ETF) -> ETF:
    """Add an ETF to the universe (or return the known one with the same ISIN).

    Raises ValueError if the ticker is already used by a different ISIN.
    """
    if etf.isin in _BY_ISIN:
        return ETFS[_BY_ISIN[etf.isin]]
    if etf.ticker in ETFS:
        raise ValueError(f"Ticker '{etf.ticker}' is already used by {ETFS[etf.ticker].isin}.")
    ETFS[etf.ticker] = etf
    _BY_ISIN[etf.isin] = etf.ticker
    return etf


def ticker_for_isin(isin: str) -> str | None:
    return _BY_ISIN.get(isin.strip().upper())


def resolve_ticker(key: str) -> str:
    """Ticker for a ticker or an ISIN (case-insensitive)."""
    k = key.strip().upper()
    if k in ETFS:
        return k
    if k in _BY_ISIN:
        return _BY_ISIN[k]
    raise ValueError(f"Unknown ETF '{key}'. Known tickers: {', '.join(ETFS)}. "
                     f"To add one from Curvo: portfolio data add {key}")


def normalize_alloc(alloc: Mapping[str, float]) -> dict[str, float]:
    """Validate an allocation and return it as {ticker: percent} in registry order, non-zero weights only.

    Raises ValueError for unknown ETFs, negative weights or a total other than 100 %.
    """
    out: dict[str, float] = {}
    for key, pct in alloc.items():
        ticker = resolve_ticker(key)
        out[ticker] = out.get(ticker, 0.0) + float(pct)
    if any(v < 0 for v in out.values()):
        raise ValueError("Negative allocations are not supported.")
    total = sum(out.values())
    if abs(total - 100) > 1e-6:
        raise ValueError(f"Allocations sum to {total:g}%, they must sum to 100%.")
    return {t: out[t] for t in ETFS if out.get(t, 0) > 0}


def parse_alloc_args(items: Sequence[str]) -> dict[str, float]:
    """Parse command-line entries like ``["UETW=60", "SXRQ=40"]`` (not yet validated)."""
    alloc: dict[str, float] = {}
    for item in items:
        key, _, pct = item.partition("=")
        if not pct:
            raise ValueError(f"Bad allocation entry '{item}'. Use TICKER=percent, tickers: {', '.join(ETFS)}")
        alloc[key.strip()] = alloc.get(key.strip(), 0.0) + float(pct)
    return alloc
