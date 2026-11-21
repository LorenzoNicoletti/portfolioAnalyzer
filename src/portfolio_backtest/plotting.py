"""Plot style helpers and the single-portfolio chart."""

from __future__ import annotations

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd

from .engine import DEFAULT_REBALANCE, BacktestResults


def jet(n: int) -> list:
    """n colours spread evenly over the jet colour scale (blue -> cyan -> green -> yellow -> red)."""
    t = np.linspace(0, 1, n) if n > 1 else np.array([0.5])
    return [plt.get_cmap("jet")(v) for v in t]


def use_style() -> None:
    plt.rcParams["font.family"] = "Arial"


def frame(ax) -> None:
    """Light grid and a black frame."""
    ax.grid(True, color="#dddddd", lw=0.6)
    for sp in ax.spines.values():
        sp.set_color("black")
        sp.set_linewidth(1.25)


def plot_backtest(res: BacktestResults, invest: float, rebalance: str = DEFAULT_REBALANCE,
                  show_single: bool = True):
    """Value over time of the portfolio (row 0 of res) and, optionally, each ETF alone (rows 1 + j),
    as returned by PortfolioAnalyzer.backtest. Returns the figure."""
    use_style()
    port = pd.Series(res.values[:, 0], index=res.dates)
    final, cagr, vol, mdd = res.final_value[0], res.cagr[0], res.volatility[0], res.max_drawdown[0]
    fig, ax = plt.subplots(figsize=(11, 6.5))
    if show_single:
        for j, (col, c) in enumerate(zip(jet(len(res.etfs)), res.etfs)):
            ax.plot(res.dates, res.values[:, 1 + j], color=col, lw=1.4,
                    label=f"{c} alone ({res.allocs[0, j]:g}%)")
    ax.plot(port.index, port, color="black", lw=2.4, label="Portfolio")
    ax.axhline(invest, color="grey", lw=0.8, ls="--")

    ax.annotate(f"€{final:,.0f}", xy=(port.index[-1], final), xytext=(6, 0),
                textcoords="offset points", va="center", fontweight="bold")
    mix = "  ·  ".join(f"{t} {p:g}%" for t, p in zip(res.etfs, res.allocs[0]))
    ax.set_title(f"Portfolio backtest: {mix}\n"
                 f"€{invest:,.0f} invested {port.index[0]:%b %Y}, {rebalance} rebalancing",
                 fontsize=12, fontweight="bold")
    ax.set_ylabel("Value (EUR)")
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"€{v:,.0f}"))
    span = port.index[-1] - port.index[0]
    ax.set_xlim(port.index[0] - span * 0.01, port.index[-1] + span * 0.09)  # room for the final value label
    frame(ax)

    dd_date = (port / port.cummax() - 1).idxmin()
    box = (f"Final value  €{final:,.0f}\n"
           f"CAGR          {cagr:.1%}\n"
           f"Volatility    {vol:.1%}\n"
           f"Max drawdown {mdd:.1%} ({dd_date:%b %Y})")
    ax.text(0.015, 0.97, box, transform=ax.transAxes, va="top", family="monospace", fontsize=9,
            bbox=dict(boxstyle="round", fc="white", ec="black", lw=0.8))
    ax.legend(loc="upper left", bbox_to_anchor=(0.0, 0.78), fontsize=8.5, frameon=True)
    fig.tight_layout()
    return fig
