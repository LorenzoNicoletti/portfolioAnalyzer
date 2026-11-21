"""Command line: build and extend the data workbook from Curvo Backtest.

    portfolio-data update                   create the workbook with the built-in ETFs, or refresh every series
    portfolio-data add EUNL                 add an ETF by ticker; its code is the ticker (EUNL)
    portfolio-data add IE00B5BMR087=SP500I  add by ISIN with your own code
    portfolio-data list                     the ETFs in the workbook and their codes

Added ETFs can then be used by their code in portfolio-backtest --alloc and portfolio-sobol --etfs / --mix.
"""

from __future__ import annotations

import argparse

from .curvo import CURVO_MCP_URL, CurvoError, add_etfs, parse_add_args, update_all
from .data import data_path, load_prices, read_workbook
from .etfs import code_for_isin


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="portfolio-data", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=None, help="path to the data workbook")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("update", help="create the workbook, or download every series again")
    add = sub.add_parser("add", help="add ETFs from Curvo by ticker or ISIN")
    add.add_argument("etfs", nargs="+", metavar="TICKER_OR_ISIN[=CODE]")
    sub.add_parser("list", help="show the ETFs in the workbook")
    return ap


def print_list(path) -> None:
    load_prices(path)  # registers the codes
    prices, info = read_workbook(data_path(path))
    print(f"\n{data_path(path)}\n")
    print(f"{'Code':10}{'ISIN':14}{'From':>9}{'To':>9}  Fund")
    for isin in prices.columns:
        row = info.loc[isin] if isin in info.index else {}
        s = prices[isin].dropna()
        print(f"{code_for_isin(isin) or isin:10}{isin:14}{s.index[0]:%Y-%m}  {s.index[-1]:%Y-%m}  {row.get('Fund', '')}")
    print()


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "update":
            print(f"Downloading from Curvo Backtest ({CURVO_MCP_URL}) ...")
            isins = update_all(args.data)
            print(f"Updated {len(isins)} series.")
            print_list(args.data)
        elif args.command == "add":
            print(f"Downloading from Curvo Backtest ({CURVO_MCP_URL}) ...")
            added = add_etfs(parse_add_args(args.etfs), args.data)
            for code, isin in added:
                print(f"  added {code} ({isin})")
            print_list(args.data)
        else:
            print_list(args.data)
    except (CurvoError, ValueError, FileNotFoundError) as e:
        raise SystemExit(str(e))


if __name__ == "__main__":
    main()
