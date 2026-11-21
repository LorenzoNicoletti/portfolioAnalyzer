"""Backtest fixed-weight ETF portfolios on monthly EUR series from Curvo Backtest."""

from .data import load_prices
from .engine import BacktestResult, BacktestResults, backtest, perform_backtest, simulate_values
from .etfs import CODES, DEFAULT_ALLOC, ETFS, normalize_alloc

__all__ = [
    "BacktestResult", "BacktestResults", "CODES", "DEFAULT_ALLOC", "ETFS",
    "backtest", "load_prices", "normalize_alloc", "perform_backtest", "simulate_values",
]
__version__ = "0.1.0"
