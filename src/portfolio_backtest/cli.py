"""Command line: backtest one portfolio, print a summary table and plot it.

    portfolio-backtest
    portfolio-backtest --invest 25000
    portfolio-backtest --alloc WORLD=50 EM=10 BONDS=30 GOLD=10
    portfolio-backtest --rebalance none --start 2010-01

ETF codes (an ISIN works too): EM, WORLD, SP500, BONDS, GOLD, EUROPE.
Data: Curvo Backtest, index-based simulation minus TER (not actual fund prices).
Past performance does not guarantee future results.
"""

from __future__ import annotations

import argparse

from .data import load_prices
from .engine import DEFAULT_INVEST, DEFAULT_REBALANCE, DEFAULT_START, REBALANCE_MONTHS, BacktestResult, backtest
from .etfs import DEFAULT_ALLOC, ETFS, normalize_alloc, parse_alloc_args

SOURCE_NOTE = ("Source: Curvo Backtest (curvo.eu/backtest). Simulated from each index minus TER, "
               "not actual fund prices.\nPast performance does not guarantee future results.")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="portfolio-backtest", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--alloc", nargs="+", metavar="CODE=PCT",
                    help="target weights in percent, e.g. WORLD=80 BONDS=20 (default: WORLD=60 BONDS=40)")
    ap.add_argument("--invest", type=float, default=DEFAULT_INVEST, help="starting lump sum in EUR (default 10000)")
    ap.add_argument("--start", default=DEFAULT_START, help=f"start month YYYY-MM (default {DEFAULT_START})")
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
    print(f"\n{'':26}{'Final EUR':>12}{'CAGR':>8}{'Vol':>8}{'Max DD':>9}")
    for name, r in rows:
        print(f"{name:26}{r.final_value:>12,.0f}{r.cagr:>8.1%}{r.volatility:>8.1%}{r.max_drawdown:>9.1%}")
    print(f"\n{SOURCE_NOTE}\n")


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        alloc = normalize_alloc(parse_alloc_args(args.alloc) if args.alloc else DEFAULT_ALLOC)
        prices = load_prices(args.data)
        run = lambda a: backtest(args.invest, a, args.start, args.end, args.rebalance, prices=prices)  # noqa: E731
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
