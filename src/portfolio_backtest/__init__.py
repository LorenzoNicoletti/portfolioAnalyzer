"""Backtest fixed-weight ETF portfolios on monthly EUR series from Curvo Backtest."""

from .curvo import add_etfs, update_all
from .data import common_start, load_prices
from .engine import BacktestResult, BacktestResults, backtest, perform_backtest, simulate_values
from .etfs import CODES, DEFAULT_ALLOC, ETFS, normalize_alloc, register

__all__ = [
    "BacktestResult", "BacktestResults", "CODES", "DEFAULT_ALLOC", "ETFS", "add_etfs", "backtest",
    "common_start", "load_prices", "normalize_alloc", "perform_backtest", "register", "simulate_values",
    "update_all",
]
__version__ = "0.1.0"
