"""Plot style helpers and the single-portfolio chart."""

from __future__ import annotations

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd

from .engine import DEFAULT_REBALANCE, BacktestResult
from .etfs import ETFS


def jet(n: int) -> list[tuple[float, float, float]]:
    """MATLAB jet colours sampled evenly over n items."""
    t = np.linspace(0, 1, n) if n > 1 else np.array([0.5])
    clip = lambda x: float(np.clip(x, 0, 1))  # noqa: E731
    return [(clip(1.5 - abs(4 * v - 3)), clip(1.5 - abs(4 * v - 2)), clip(1.5 - abs(4 * v - 1))) for v in t]


def use_style() -> None:
    plt.rcParams["font.family"] = "Arial"


def frame(ax) -> None:
    """Light grid and a black frame."""
    ax.grid(True, color="#dddddd", lw=0.6)
    for sp in ax.spines.values():
        sp.set_color("black")
        sp.set_linewidth(1.25)


def plot_backtest(res: BacktestResult, invest: float, alloc: dict[str, float], prices: pd.DataFrame,
                  rebalance: str = DEFAULT_REBALANCE, show_single: bool = True):
    """Portfolio value over time, optionally with each held ETF alone. Returns the figure."""
    use_style()
    port = res.values
    px = prices.loc[port.index]
    fig, ax = plt.subplots(figsize=(11, 6.5))
    if show_single:
        for col, (c, pct) in zip(jet(len(alloc)), alloc.items()):
            ser = invest * px[c] / px[c].iloc[0]
            ax.plot(ser.index, ser, color=col, lw=1, alpha=0.8, label=f"{ETFS[c].name} alone ({pct:g}%)")
    ax.plot(port.index, port, color="black", lw=2.4, label="Portfolio")
    ax.axhline(invest, color="grey", lw=0.8, ls="--")

    ax.annotate(f"€{res.final_value:,.0f}", xy=(port.index[-1], res.final_value), xytext=(6, 0),
                textcoords="offset points", va="center", fontweight="bold")
    ax.set_title(f"Portfolio backtest: €{invest:,.0f} invested {port.index[0]:%b %Y}, "
                 f"{rebalance} rebalancing", fontsize=13, fontweight="bold")
    ax.set_ylabel("Value (EUR)")
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"€{v:,.0f}"))
    ax.margins(x=0.01)
    frame(ax)

    dd_date = (port / port.cummax() - 1).idxmin()
    box = (f"Final value  €{res.final_value:,.0f}\n"
           f"CAGR          {res.cagr:.1%}\n"
           f"Volatility    {res.volatility:.1%}\n"
           f"Max drawdown {res.max_drawdown:.1%} ({dd_date:%b %Y})")
    ax.text(0.015, 0.97, box, transform=ax.transAxes, va="top", family="monospace", fontsize=9,
            bbox=dict(boxstyle="round", fc="white", ec="black", lw=0.8))
    ax.legend(loc="upper left", bbox_to_anchor=(0.0, 0.78), fontsize=8.5, frameon=True)
    fig.tight_layout()
    return fig
