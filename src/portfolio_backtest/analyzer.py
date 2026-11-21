"""PortfolioAnalyzer: one object for the data, the backtest and the Sobol study.

    from portfolio_backtest import PortfolioAnalyzer

    pa = PortfolioAnalyzer()                  # basis allocation, 10,000 EUR, annual rebalancing
    pa.update_data()                          # create / refresh the data workbook from Curvo
    pa.add_etfs("EUNL", "IE00B5BMR087=SXR8")  # add ETFs by ticker or ISIN (=TICKER picks the fund's ticker)
    pa.list_etfs()                            # the ETFs in the workbook
    pa.backtest()                             # table + chart of the allocation and each ETF alone
    pa.sobol(["UETW", "SXRQ", "PPFB"])        # interactive volatility vs CAGR cloud

The settings (allocation, amount, period, rebalancing, data file) are attributes and can be changed
between calls, e.g. ``pa.alloc = {"UETW": 60, "SXRQ": 40}``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pandas as pd

from .curvo import CURVO_MCP_URL, add_etfs, parse_add_args, update_all
from .data import common_start, data_path, load_prices, read_workbook
from .engine import DEFAULT_INVEST, DEFAULT_REBALANCE, REBALANCE_MONTHS, BacktestResults, perform_backtest
from .etfs import DEFAULT_ALLOC, ETFS, normalize_alloc, resolve_ticker
from .sobol.study import SobolStudy, run_study

DEFAULT_SOBOL_ETFS = ("AEME", "UETW", "SXRQ", "PPFB", "LYP6")
DEFAULT_SAMPLES = 8192
SOURCE_NOTE = ("Source: Curvo Backtest (curvo.eu/backtest). Simulated from each index minus TER, "
               "not actual fund prices.\nPast performance does not guarantee future results.")


class PortfolioAnalyzer:
    def __init__(self, alloc: Mapping[str, float] | None = None, invest: float = DEFAULT_INVEST,
                 start: str | None = None, end: str | None = None, rebalance: str = DEFAULT_REBALANCE,
                 data: str | Path | None = None):
        """
        alloc:     {ticker or ISIN: %}, sums to 100 (default: the basis allocation DEFAULT_ALLOC)
        invest:    lump sum in EUR
        start/end: "YYYY-MM"; start default = first month in which every ETF involved has data
        rebalance: none, monthly, quarterly, semiannual or annual
        data:      path to the data workbook (default: data/Curvo_ETF_Monthly_EUR.xlsx)
        """
        if rebalance not in REBALANCE_MONTHS:
            raise ValueError(f"Unknown rebalance '{rebalance}'. Use one of: {', '.join(REBALANCE_MONTHS)}")
        self.alloc = dict(alloc or DEFAULT_ALLOC)
        self.invest = invest
        self.start = start
        self.end = end
        self.rebalance = rebalance
        self.data = data

    def __repr__(self) -> str:
        mix = ", ".join(f"{c} {p:g}%" for c, p in self.alloc.items())
        return (f"PortfolioAnalyzer({mix}; EUR {self.invest:,.0f}, {self.start or 'auto'} - {self.end or 'end'}, "
                f"{self.rebalance} rebalancing)")

    # --------------------------------------------------------------------- data --
    @property
    def prices(self) -> pd.DataFrame:
        """All monthly EUR series, columns = tickers (loading also registers the added ETFs)."""
        return load_prices(self.data)

    def _mix(self) -> dict[str, float]:
        """The validated allocation; the prices are loaded first so that added tickers are known."""
        self.prices
        return normalize_alloc(self.alloc)

    def update_data(self) -> list[str]:
        """Create the workbook with the built-in ETFs, or download every series in it again."""
        print(f"Downloading from Curvo Backtest ({CURVO_MCP_URL}) ...")
        return update_all(self.data)

    def add_etfs(self, *etfs: str) -> list[tuple[str, str]]:
        """Add ETFs from Curvo by ticker ("EUNL") or ISIN ("IE00B5BMR087", or "IE00B5BMR087=SXR8" to pick which
        of the fund's tickers to use; default: its first one). Returns [(ticker, ISIN)]."""
        print(f"Downloading from Curvo Backtest ({CURVO_MCP_URL}) ...")
        return add_etfs(parse_add_args(etfs), self.data)

    def list_etfs(self) -> pd.DataFrame:
        """The ETFs in the workbook: ticker, ISIN, first and last month, fund name."""
        prices = self.prices
        _, info = read_workbook(data_path(self.data))
        rows = []
        for ticker in prices.columns:
            etf, s = ETFS[ticker], prices[ticker].dropna()
            fund = info["Fund"].get(etf.isin) if "Fund" in info.columns else None
            rows.append({"ticker": ticker, "isin": etf.isin, "from": f"{s.index[0]:%Y-%m}",
                         "to": f"{s.index[-1]:%Y-%m}", "fund": fund if isinstance(fund, str) else etf.name})
        return pd.DataFrame(rows).set_index("ticker")

    # ----------------------------------------------------------------- backtest --
    def backtest(self, report: bool = True, plot: bool = True, show_single: bool = True) -> BacktestResults:
        """Backtest the allocation; row 0 of the result is the portfolio, row 1 + j the j-th held ETF alone.

        All rows start in the same month. report prints the table, plot shows the chart.
        """
        mix = self._mix()
        held = list(mix)
        start = self.start or common_start(self.prices, held)
        allocs = [list(mix.values())] + [[100 if c == h else 0 for c in held] for h in held]
        res = perform_backtest(self.invest, held, allocs, start, self.end, self.rebalance,
                               keep_values=True, prices=self.prices)
        if report:
            self._print_report(res)
        if plot:
            import matplotlib.pyplot as plt

            from .plotting import plot_backtest

            plot_backtest(res, self.invest, self.rebalance, show_single=show_single)
            plt.show()
        return res

    def _print_report(self, res: BacktestResults) -> None:
        years = (len(res.dates) - 1) / 12
        print(f"\nPeriod      {res.dates[0]:%b %Y} - {res.dates[-1]:%b %Y}  ({years:.1f} years)")
        print(f"Invested    EUR {self.invest:,.0f}   rebalancing: {self.rebalance}")
        print("Allocation  " + ", ".join(f"{c} {p:g}%" for c, p in zip(res.etfs, res.allocs[0])))
        names = ["Portfolio"] + [f"{t}  {ETFS[t].name}" for t in res.etfs]
        w = min(max(26, *(len(n) + 2 for n in names)), 48)  # name column fits the longest name
        print(f"\n{'':{w}}{'Final EUR':>12}{'CAGR':>8}{'Vol':>8}{'Max DD':>9}")
        for i, n in enumerate(names):
            print(f"{n[:w - 2]:{w}}{res.final_value[i]:>12,.0f}{res.cagr[i]:>8.1%}"
                  f"{res.volatility[i]:>8.1%}{res.max_drawdown[i]:>9.1%}")
        print(f"\n{SOURCE_NOTE}\n")

    # -------------------------------------------------------------------- sobol --
    def sobol(self, etfs: Sequence[str] = DEFAULT_SOBOL_ETFS, n_samples: int = DEFAULT_SAMPLES, seed: int = 42,
              filters: Mapping[str, tuple[float, float]] | None = None, plot: bool = True) -> SobolStudy:
        """Sobol study over the mixes of etfs, with the allocation as the white reference diamond.

        filters: filters active when the chart opens, {ticker: (min %, max %)}, e.g. {"PPFB": (10, 30)}.
        Default start: first month in which every ETF of the study and of the allocation has data.
        """
        mix = self._mix()
        etfs = [resolve_ticker(e) for e in etfs]
        filters = {resolve_ticker(t): rng for t, rng in (filters or {}).items()}
        start = self.start or common_start(self.prices, etfs + list(mix))  # cloud and mix: same period
        study = run_study(etfs, n_samples, seed, self.invest, start, self.end, self.rebalance, prices=self.prices)
        if plot:
            import matplotlib.pyplot as plt

            from .sobol.explorer import SobolExplorer

            self._explorer = SobolExplorer(study, mix, self.invest, start, self.end, self.rebalance,
                                           filters=filters, prices=self.prices)  # kept alive for the widgets
            plt.show()
        return study
