"""The ETF universe and allocation handling.

An allocation maps ETF codes (or ISINs) to percentages that sum to 100, e.g.
``{"WORLD": 60, "BONDS": 40}``. A plain sequence of numbers is read in ``CODES`` order.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ETF:
    code: str
    isin: str
    name: str


ETFS: dict[str, ETF] = {
    e.code: e
    for e in (
        ETF("EM", "LU1437017350", "Amundi MSCI EM"),
        ETF("WORLD", "IE00BD4TXV59", "UBS MSCI World"),
        ETF("SP500", "IE00BFMXXD54", "Vanguard S&P 500"),
        ETF("BONDS", "IE00B3VTN290", "iShares EUR Govt 7-10yr"),
        ETF("GOLD", "IE00B4ND3602", "iShares Physical Gold"),
        ETF("EUROPE", "LU0908500753", "Amundi Stoxx Europe 600"),
    )
}
CODES: tuple[str, ...] = tuple(ETFS)
_BY_ISIN = {e.isin: e.code for e in ETFS.values()}

# Generic example used when no allocation is given; pass --alloc / --mix for your own.
DEFAULT_ALLOC: dict[str, float] = {"WORLD": 60, "BONDS": 40}

Allocation = Mapping[str, float] | Sequence[float]


def resolve_code(key: str) -> str:
    """ETF code for a code or an ISIN (case-insensitive)."""
    k = key.strip().upper()
    if k in ETFS:
        return k
    if k in _BY_ISIN:
        return _BY_ISIN[k]
    raise ValueError(f"Unknown ETF '{key}'. Codes: {', '.join(CODES)}")


def normalize_alloc(alloc: Allocation) -> dict[str, float]:
    """Validate an allocation and return it as {code: percent} in CODES order, non-zero weights only.

    Raises ValueError for unknown ETFs, negative weights or a total other than 100 %.
    """
    if isinstance(alloc, Mapping):
        out: dict[str, float] = {}
        for key, pct in alloc.items():
            code = resolve_code(key)
            out[code] = out.get(code, 0.0) + float(pct)
    else:
        values = [float(x) for x in alloc]
        if len(values) != len(CODES):
            raise ValueError(f"Need {len(CODES)} allocations in order {list(CODES)}, got {len(values)}")
        out = dict(zip(CODES, values))
    if any(v < 0 for v in out.values()):
        raise ValueError("Negative allocations are not supported.")
    total = sum(out.values())
    if abs(total - 100) > 1e-6:
        raise ValueError(f"Allocations sum to {total:g}%, they must sum to 100%.")
    return {c: out[c] for c in CODES if out.get(c, 0) > 0}


def parse_alloc_args(items: Sequence[str]) -> dict[str, float]:
    """Parse command-line entries like ``["WORLD=60", "BONDS=40"]`` (not yet validated)."""
    alloc: dict[str, float] = {}
    for item in items:
        key, _, pct = item.partition("=")
        if not pct:
            raise ValueError(f"Bad allocation entry '{item}'. Use CODE=percent, codes: {', '.join(CODES)}")
        alloc[key.strip()] = alloc.get(key.strip(), 0.0) + float(pct)
    return alloc
