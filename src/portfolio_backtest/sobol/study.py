"""Sobol study: spread portfolios evenly over all mixes of a set of ETFs and backtest them.

1. A scrambled Sobol set in d = len(etfs) dimensions; its first n points u in [0,1)^d are taken
   (MATLAB: p = scramble(sobolset(d), 'MatousekAffineOwen'); U = net(p, n)).
2. Each point becomes weights summing to 100 %:  e = -ln(1 - u),  w = 100 * e / sum(e).
   This is uniform over the simplex, so every possible mix is equally likely.
3. The 100 %-in-one-ETF portfolios are appended as reference points.
"""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import qmc

from ..engine import DEFAULT_INVEST, DEFAULT_REBALANCE, DEFAULT_START, BacktestResults, perform_backtest
from ..etfs import resolve_code


def sobol_allocations(n: int, d: int, seed: int | None = 42) -> np.ndarray:
    """(n, d) allocations in %, evenly spread over all mixes. Powers of 2 for n spread most evenly."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", "The balance properties of Sobol")  # n need not be a power of 2
        u = qmc.Sobol(d=d, scramble=True, seed=seed).random(n)
    e = -np.log1p(-u)
    return 100 * e / e.sum(axis=1, keepdims=True)


@dataclass
class SobolStudy:
    etfs: list[str]
    n_samples: int           # rows [0, n_samples) are Sobol portfolios, the rest are the single ETFs
    result: BacktestResults

    @property
    def allocs(self) -> np.ndarray:
        return self.result.allocs

    @property
    def ratio(self) -> np.ndarray:
        """Return per unit of risk (CAGR / volatility)."""
        return self.result.cagr / self.result.volatility

    @property
    def singles(self) -> np.ndarray:
        return np.arange(self.n_samples, len(self.allocs))

    def picks(self) -> dict[str, int]:
        """Index of the notable portfolios."""
        return {"Highest CAGR": int(self.result.cagr.argmax()),
                "Lowest volatility": int(self.result.volatility.argmin()),
                "Best CAGR / volatility": int(self.ratio.argmax())}


def run_study(etfs: Sequence[str], n_samples: int = 8192, seed: int | None = 42,
              invest: float = DEFAULT_INVEST, start: str = DEFAULT_START, end: str | None = None,
              rebalance: str = DEFAULT_REBALANCE, prices: pd.DataFrame | None = None) -> SobolStudy:
    etfs = [resolve_code(e) for e in etfs]
    allocs = np.vstack([sobol_allocations(n_samples, len(etfs), seed),
                        100 * np.eye(len(etfs))])
    result = perform_backtest(invest, etfs, allocs, start, end, rebalance, prices=prices)
    return SobolStudy(etfs=etfs, n_samples=n_samples, result=result)
