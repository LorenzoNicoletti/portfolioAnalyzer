"""Command line: run a Sobol study and open the interactive chart.

    portfolio-sobol                                      EM, WORLD, BONDS, GOLD, EUROPE; your default mix as the white diamond
    portfolio-sobol --etfs WORLD BONDS GOLD --samples 4096
    portfolio-sobol --filter GOLD=25-100 --rebalance quarterly
"""

from __future__ import annotations

import argparse

from ..data import common_start, load_prices
from ..engine import DEFAULT_INVEST, DEFAULT_REBALANCE, DEFAULT_START, REBALANCE_MONTHS
from ..etfs import DEFAULT_ALLOC, normalize_alloc, parse_alloc_args, resolve_code
from .study import run_study

DEFAULT_STUDY_ETFS = ("EM", "WORLD", "BONDS", "GOLD", "EUROPE")


def parse_filters(items: list[str]) -> dict[str, tuple[float, float]]:
    """["GOLD=25-100"] -> {"GOLD": (25.0, 100.0)}"""
    out = {}
    for item in items:
        key, _, rng = item.partition("=")
        lo, sep, hi = rng.partition("-")
        if not sep:
            raise ValueError(f"Bad filter '{item}'. Use CODE=min-max, e.g. GOLD=25-100")
        out[resolve_code(key)] = (float(lo), float(hi))
    return out


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="portfolio-sobol", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--etfs", nargs="+", default=list(DEFAULT_STUDY_ETFS), help="ETFs in the study")
    ap.add_argument("--samples", type=int, default=8192, help="number of Sobol portfolios (default 8192)")
    ap.add_argument("--seed", type=int, default=42, help="scrambling seed (default 42)")
    ap.add_argument("--mix", nargs="+", metavar="CODE=PCT", help="reference mix shown as a white diamond "
                    "(default: " + " ".join(f"{c}={p:g}" for c, p in DEFAULT_ALLOC.items()) + ")")
    ap.add_argument("--filter", nargs="+", default=[], metavar="CODE=MIN-MAX", help="filters active at start")
    ap.add_argument("--invest", type=float, default=DEFAULT_INVEST)
    ap.add_argument("--start", default=DEFAULT_START,
                    help="start month YYYY-MM (default: first month in which every ETF of the study and the mix has data)")
    ap.add_argument("--end", default=None)
    ap.add_argument("--rebalance", choices=REBALANCE_MONTHS, default=DEFAULT_REBALANCE)
    ap.add_argument("--data", default=None, help="path to the Curvo price workbook")
    return ap


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        prices = load_prices(args.data)
        mix = normalize_alloc(parse_alloc_args(args.mix) if args.mix else DEFAULT_ALLOC)
        filters = parse_filters(args.filter)
        etfs = [resolve_code(e) for e in args.etfs]
        start = args.start or common_start(prices, etfs + list(mix))  # cloud and mix over the same period
        study = run_study(etfs, args.samples, args.seed, args.invest, start, args.end,
                          args.rebalance, prices=prices)
    except (ValueError, FileNotFoundError) as e:
        raise SystemExit(str(e))

    import matplotlib.pyplot as plt

    from .explorer import SobolExplorer

    explorer = SobolExplorer(study, mix, args.invest, start, args.end, args.rebalance,  # noqa: F841
                             filters=filters, prices=prices)
    plt.show()


if __name__ == "__main__":
    main()
