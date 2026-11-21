"""Backtest fixed-weight ETF portfolios on monthly EUR series from Curvo Backtest.

Everything goes through PortfolioAnalyzer (see analyzer.py); on the command line through ``portfolio``.
"""

from .analyzer import PortfolioAnalyzer
from .engine import BacktestResults, perform_backtest
from .etfs import DEFAULT_ALLOC

__all__ = ["BacktestResults", "DEFAULT_ALLOC", "PortfolioAnalyzer", "perform_backtest"]
__version__ = "0.2.0"
