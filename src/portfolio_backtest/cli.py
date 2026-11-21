"""Command line for PortfolioAnalyzer: one command, one subcommand per method.

    portfolio data update                       create the workbook from Curvo, or download every series again
    portfolio data add EUNL IE00B5BMR087=SXR8   add ETFs by ticker or ISIN (ISIN=TICKER picks the fund's ticker)
    portfolio data list                         the ETFs in the workbook

    portfolio backtest                          the basis allocation: table + chart
    portfolio backtest --alloc UETW=50 AEME=10 SXRQ=30 PPFB=10 --invest 25000 --rebalance none

    portfolio sobol                             AEME, UETW, SXRQ, PPFB, LYP6; the allocation as the white diamond
    portfolio sobol --etfs UETW SXRQ PPFB --samples 4096 --filter PPFB=10-30

Options shared by backtest and sobol: --alloc --invest --start --end --rebalance --data.
Data: Curvo Backtest, index-based simulation minus TER (not actual fund prices).
Past performance does not guarantee future results.
"""

from __future__ import annotations

import argparse

from .analyzer import DEFAULT_SAMPLES, DEFAULT_SOBOL_ETFS, PortfolioAnalyzer
from .curvo import CurvoError
from .engine import DEFAULT_INVEST, DEFAULT_REBALANCE, REBALANCE_MONTHS
from .etfs import DEFAULT_ALLOC, parse_alloc_args


def parse_filters(items: list[str]) -> dict[str, tuple[float, float]]:
    """["PPFB=25-100"] -> {"PPFB": (25.0, 100.0)}"""
    out = {}
    for item in items:
        key, _, rng = item.partition("=")
        lo, sep, hi = rng.partition("-")
        if not sep:
            raise ValueError(f"Bad filter '{item}'. Use TICKER=min-max, e.g. PPFB=25-100")
        out[key.strip().upper()] = (float(lo), float(hi))
    return out


def build_parser() -> argparse.ArgumentParser:
    data = argparse.ArgumentParser(add_help=False)
    data.add_argument("--data", default=None, help="path to the data workbook")

    settings = argparse.ArgumentParser(add_help=False, parents=[data])
    settings.add_argument("--alloc", nargs="+", metavar="TICKER=PCT",
                          help="weights in percent, e.g. UETW=80 SXRQ=20 "
                               "(default: " + " ".join(f"{c}={p:g}" for c, p in DEFAULT_ALLOC.items()) + ")")
    settings.add_argument("--invest", type=float, default=DEFAULT_INVEST, help="lump sum in EUR (default 10000)")
    settings.add_argument("--start", help="start month YYYY-MM (default: first month every ETF involved has data)")
    settings.add_argument("--end", help="end month YYYY-MM (default: last available)")
    settings.add_argument("--rebalance", choices=REBALANCE_MONTHS, default=DEFAULT_REBALANCE,
                          help=f"how often to reset to the target weights (default {DEFAULT_REBALANCE})")

    ap = argparse.ArgumentParser(prog="portfolio", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    d = sub.add_parser("data", help="create, extend or list the data workbook (Curvo)")
    dsub = d.add_subparsers(dest="action", required=True)
    dsub.add_parser("update", parents=[data], help="create the workbook, or download every series again")
    add = dsub.add_parser("add", parents=[data], help="add ETFs by ticker or ISIN")
    add.add_argument("etfs", nargs="+", metavar="TICKER_OR_ISIN[=TICKER]")
    dsub.add_parser("list", parents=[data], help="show the ETFs in the workbook")

    b = sub.add_parser("backtest", parents=[settings], help="backtest the allocation: table + chart")
    b.add_argument("--no-single", action="store_true", help="hide the single-ETF lines in the chart")
    b.add_argument("--no-plot", action="store_true", help="only print the table")

    s = sub.add_parser("sobol", parents=[settings], help="interactive Sobol study")
    s.add_argument("--etfs", nargs="+", default=list(DEFAULT_SOBOL_ETFS), help="ETFs in the study")
    s.add_argument("--samples", type=int, default=DEFAULT_SAMPLES, help=f"Sobol portfolios (default {DEFAULT_SAMPLES})")
    s.add_argument("--seed", type=int, default=42, help="scrambling seed (default 42)")
    s.add_argument("--filter", nargs="+", default=[], metavar="TICKER=MIN-MAX", help="filters active at start")
    return ap


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "data":
            pa = PortfolioAnalyzer(data=args.data)
            if args.action == "update":
                print(f"Updated {len(pa.update_data())} series.")
            elif args.action == "add":
                for ticker, isin in pa.add_etfs(*args.etfs):
                    print(f"  added {ticker} ({isin})")
            print(f"\n{pa.list_etfs().to_string()}\n")
            return

        alloc = parse_alloc_args(args.alloc) if args.alloc else None
        pa = PortfolioAnalyzer(alloc, args.invest, args.start, args.end, args.rebalance, args.data)
        if args.command == "backtest":
            pa.backtest(plot=not args.no_plot, show_single=not args.no_single)
        else:
            pa.sobol(args.etfs, args.samples, args.seed, parse_filters(args.filter))
    except (CurvoError, ValueError, FileNotFoundError) as e:
        raise SystemExit(str(e))


if __name__ == "__main__":
    main()
