"""Vectorised backtest of fixed-weight portfolios with periodic rebalancing."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .data import common_start, load_prices, window
from .etfs import Allocation, normalize_alloc, resolve_code

DEFAULT_INVEST = 10_000    # EUR
DEFAULT_START: str | None = None  # None: first month in which every held ETF has data
DEFAULT_REBALANCE = "annual"
REBALANCE_MONTHS: dict[str, int | None] = {
    "none": None, "monthly": 1, "quarterly": 3, "semiannual": 6, "annual": 12,
}


@dataclass
class BacktestResults:
    """Many portfolios at once: one entry per portfolio (arrays of length N)."""
    etfs: list[str]           # ETF codes, column j of allocs is etfs[j]
    allocs: np.ndarray        # (N, K) allocations in %
    final_value: np.ndarray   # (N,) EUR
    cagr: np.ndarray          # (N,) compound annual growth rate, 0.079 = 7.9 %
    volatility: np.ndarray    # (N,) annualised std of monthly returns
    max_drawdown: np.ndarray  # (N,) worst peak-to-trough fall, e.g. -0.317
    dates: pd.DatetimeIndex = field(repr=False)
    values: np.ndarray | None = field(default=None, repr=False)  # (T, N) EUR, if keep_values=True


@dataclass
class BacktestResult:
    """A single portfolio."""
    final_value: float
    cagr: float
    volatility: float
    max_drawdown: float
    values: pd.Series = field(repr=False)  # monthly portfolio value in EUR


def simulate_values(invest: float, weights: np.ndarray, prices: np.ndarray,
                    rebalance_every: int | None) -> np.ndarray:
    """Portfolio values without looping over portfolios or months.

    weights: (N, K) fractions summing to 1; prices: (T, K); returns (T, N) in EUR.

    Between rebalancing dates each portfolio is buy-and-hold, so with s(t) the last
    rebalancing month before t:
        V(t) = V(s(t)) * sum_i w_i * P_i(t) / P_i(s(t))
    and V at the rebalancing months is the running product of those period growths.
    This gives exactly the same numbers as stepping month by month.
    """
    T = len(prices)
    t = np.arange(T)
    if rebalance_every:
        s = np.maximum(t - 1, 0) // rebalance_every * rebalance_every  # last rebalance strictly before t
    else:
        s = np.zeros(T, dtype=int)
    growth = (prices / prices[s]) @ weights.T          # (T, N) growth since the period start
    rebal = np.unique(s)                               # 0, k, 2k, ...
    period_growth = growth[rebal[1:]]                  # growth over each finished period
    level = np.vstack([np.ones((1, len(weights))), np.cumprod(period_growth, axis=0)])  # V(start) / invest
    return invest * level[np.searchsorted(rebal, s)] * growth


def metrics(values: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """CAGR, annualised volatility and max drawdown of monthly values (T, N)."""
    years = (len(values) - 1) / 12
    rets = values[1:] / values[:-1] - 1
    cagr = (values[-1] / values[0]) ** (1 / years) - 1
    vol = rets.std(axis=0, ddof=1) * np.sqrt(12)
    mdd = (values / np.maximum.accumulate(values, axis=0) - 1).min(axis=0)
    return cagr, vol, mdd


def perform_backtest(invest: float, etfs: Sequence[str], allocs, start: str | None = DEFAULT_START,
                     end: str | None = None, rebalance: str = DEFAULT_REBALANCE,
                     keep_values: bool = False, prices: pd.DataFrame | None = None) -> BacktestResults:
    """Backtest many portfolios at once.

    etfs:   ETF codes or ISINs, any number and order, e.g. ["WORLD", "GOLD", "BONDS"]
    allocs: (N, len(etfs)) percentages; column j is the weight of etfs[j]; each row sums to 100
    start:  "YYYY-MM"; default: the first month in which every held ETF has data
    prices: monthly price table with ETF codes as columns (default: load_prices())
    """
    prices = load_prices() if prices is None else prices  # loads first: registers the workbook's ETFs
    etfs = [resolve_code(e) for e in etfs]
    if rebalance not in REBALANCE_MONTHS:
        raise ValueError(f"Unknown rebalance '{rebalance}'. Use one of: {', '.join(REBALANCE_MONTHS)}")
    allocs = np.atleast_2d(np.asarray(allocs, dtype=float))
    if allocs.shape[1] != len(etfs):
        raise ValueError(f"{len(etfs)} ETFs given but allocations have {allocs.shape[1]} columns")
    if (allocs < 0).any():
        raise ValueError("Negative allocations are not supported.")
    bad = np.abs(allocs.sum(axis=1) - 100) > 1e-6
    if bad.any():
        raise ValueError(f"{bad.sum()} allocation(s) do not sum to 100%, e.g. {allocs[bad][0]}")

    missing_cols = [e for e in etfs if e not in prices.columns]
    if missing_cols:
        raise ValueError(f"No price series in the data for: {', '.join(missing_cols)}. "
                         f"Add it with: portfolio-data add <ticker or ISIN>")
    used = (allocs > 0).any(axis=0)
    start = start or common_start(prices, np.array(etfs)[used])
    win = window(prices, start, end)
    px = win[etfs].to_numpy(dtype=float).copy()
    missing = used & np.isnan(px[0])
    if missing.any():
        raise ValueError(f"No data at {start} for: " + ", ".join(np.array(etfs)[missing]))
    px[:, ~used] = 1.0  # columns nobody holds may be NaN; their weight is 0 anyway

    values = simulate_values(invest, allocs / 100, px, REBALANCE_MONTHS[rebalance])
    cagr, vol, mdd = metrics(values)
    return BacktestResults(etfs=etfs, allocs=allocs, final_value=values[-1], cagr=cagr, volatility=vol,
                           max_drawdown=mdd, dates=win.index, values=values if keep_values else None)


def backtest(invest: float, alloc: Allocation, start: str | None = DEFAULT_START, end: str | None = None,
             rebalance: str = DEFAULT_REBALANCE, prices: pd.DataFrame | None = None) -> BacktestResult:
    """Lump sum ``invest`` (EUR) at ``start``, held in ``alloc`` and reset to it every rebalancing period.

    alloc: e.g. {"WORLD": 60, "BONDS": 40}, or 6 percentages in order EM, WORLD, SP500, BONDS, GOLD, EUROPE.
    start: "YYYY-MM"; default: the first month in which every held ETF has data
    """
    prices = load_prices() if prices is None else prices
    a = normalize_alloc(alloc)
    r = perform_backtest(invest, list(a), [list(a.values())], start, end, rebalance,
                         keep_values=True, prices=prices)
    return BacktestResult(
        final_value=float(r.final_value[0]),
        cagr=float(r.cagr[0]),
        volatility=float(r.volatility[0]),
        max_drawdown=float(r.max_drawdown[0]),
        values=pd.Series(r.values[:, 0], index=r.dates),
    )
