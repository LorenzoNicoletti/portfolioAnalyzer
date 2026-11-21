"""Command line: backtest one portfolio, print a summary table and plot it.

    portfolio-backtest                                   default mix: EM 13, WORLD 25, SP500 10, BONDS 20, GOLD 10, EUROPE 22
    portfolio-backtest --invest 25000
    portfolio-backtest --alloc WORLD=50 EM=10 BONDS=30 GOLD=10
    portfolio-backtest --rebalance none --start 2010-01

ETF codes (an ISIN works too): EM, WORLD, SP500, BONDS, GOLD, EUROPE, plus any added with portfolio-data add.
Data: Curvo Backtest, index-based simulation minus TER (not actual fund prices).
Past performance does not guarantee future results.
"""

from __future__ import annotations

import argparse

from .data import common_start, load_prices
from .engine import DEFAULT_INVEST, DEFAULT_REBALANCE, DEFAULT_START, REBALANCE_MONTHS, BacktestResult, backtest
from .etfs import DEFAULT_ALLOC, ETFS, normalize_alloc, parse_alloc_args

SOURCE_NOTE = ("Source: Curvo Backtest (curvo.eu/backtest). Simulated from each index minus TER, "
               "not actual fund prices.\nPast performance does not guarantee future results.")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="portfolio-backtest", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--alloc", nargs="+", metavar="CODE=PCT",
                    help="target weights in percent, e.g. WORLD=80 BONDS=20 "
                         "(default: " + " ".join(f"{c}={p:g}" for c, p in DEFAULT_ALLOC.items()) + ")")
    ap.add_argument("--invest", type=float, default=DEFAULT_INVEST, help="starting lump sum in EUR (default 10000)")
    ap.add_argument("--start", default=DEFAULT_START,
                    help="start month YYYY-MM (default: first month in which every held ETF has data)")
    ap.add_argument("--end", default=None, help="end month YYYY-MM (default: last available)")
    ap.add_argument("--rebalance", choices=REBALANCE_MONTHS, default=DEFAULT_REBALANCE,
                    help=f"how often to reset to the target weights (default {DEFAULT_REBALANCE})")
    ap.add_argument("--data", default=None, help="path to the Curvo price workbook")
    ap.add_argument("--no-single", action="store_true", help="hide the single-ETF lines")
    ap.add_argument("--no-plot", action="store_true", help="only print the table")
    return ap


def print_report(invest: float, alloc: dict[str, float], rebalance: str,
                 rows: list[tuple[str, BacktestResult]]) -> None:
    port = rows[0][1].values
    years = (len(port) - 1) / 12
    print(f"\nPeriod      {port.index[0]:%b %Y} - {port.index[-1]:%b %Y}  ({years:.1f} years)")
    print(f"Invested    EUR {invest:,.0f}   rebalancing: {rebalance}")
    print("Allocation  " + ", ".join(f"{c} {pct:g}%" for c, pct in alloc.items()))
    w = min(max(26, *(len(name) + 2 for name, _ in rows)), 48)  # name column fits the longest name
    print(f"\n{'':{w}}{'Final EUR':>12}{'CAGR':>8}{'Vol':>8}{'Max DD':>9}")
    for name, r in rows:
        print(f"{name[:w - 2]:{w}}{r.final_value:>12,.0f}{r.cagr:>8.1%}{r.volatility:>8.1%}{r.max_drawdown:>9.1%}")
    print(f"\n{SOURCE_NOTE}\n")


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        prices = load_prices(args.data)  # first: registers the ETFs added to the workbook
        alloc = normalize_alloc(parse_alloc_args(args.alloc) if args.alloc else DEFAULT_ALLOC)
        start = args.start or common_start(prices, alloc)  # the single ETFs start in the same month
        run = lambda a: backtest(args.invest, a, start, args.end, args.rebalance, prices=prices)  # noqa: E731
        rows = [("Portfolio", run(alloc))] + [(ETFS[c].name, run({c: 100})) for c in alloc]
    except (ValueError, FileNotFoundError) as e:
        raise SystemExit(str(e))

    print_report(args.invest, alloc, args.rebalance, rows)
    if not args.no_plot:
        import matplotlib.pyplot as plt

        from .plotting import plot_backtest

        plot_backtest(rows[0][1], args.invest, alloc, prices, args.rebalance, show_single=not args.no_single)
        plt.show()


if __name__ == "__main__":
    main()
