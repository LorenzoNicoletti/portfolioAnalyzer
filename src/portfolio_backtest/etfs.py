"""The ETF universe and allocation handling.

Every ETF has a short code (e.g. ``WORLD``) used on the command line and in allocations.
Six ETFs are built in; ETFs added from Curvo with ``portfolio-data add`` are registered from
the data workbook when it is loaded (see data.py), so their codes work everywhere too.

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
    ticker: str = ""  # exchange ticker shown in charts; falls back to the code

    @property
    def label(self) -> str:
        """Short name for chart labels: the ticker, or the code if no ticker is known."""
        return self.ticker or self.code


BUILTIN_ETFS: tuple[ETF, ...] = (
    ETF("EM", "LU1437017350", "Amundi MSCI EM", "AEME"),
    ETF("WORLD", "IE00BD4TXV59", "UBS MSCI World", "UETW"),
    ETF("SP500", "IE00BFMXXD54", "Vanguard S&P 500", "VUAA"),
    ETF("BONDS", "IE00B3VTN290", "iShares EUR Govt 7-10yr", "SXRQ"),
    ETF("GOLD", "IE00B4ND3602", "iShares Physical Gold", "PPFB"),
    ETF("EUROPE", "LU0908500753", "Amundi Stoxx Europe 600", "LYP6"),
)

# All known ETFs: the built-in ones, plus the ones registered from the data workbook.
ETFS: dict[str, ETF] = {e.code: e for e in BUILTIN_ETFS}
CODES: tuple[str, ...] = tuple(ETFS)  # the built-in codes; order of a plain-sequence allocation
_BY_ISIN = {e.isin: e.code for e in ETFS.values()}

# Default (basis) allocation, used when no --alloc / --mix is given.
DEFAULT_ALLOC: dict[str, float] = {"EM": 13, "WORLD": 25, "SP500": 10, "BONDS": 20, "GOLD": 10, "EUROPE": 22}

Allocation = Mapping[str, float] | Sequence[float]


def register(etf: ETF) -> ETF:
    """Add an ETF to the universe (or return the known one with the same ISIN).

    Raises ValueError if the code is already used by a different ISIN.
    """
    if etf.isin in _BY_ISIN:
        return ETFS[_BY_ISIN[etf.isin]]
    if etf.code in ETFS:
        raise ValueError(f"Code '{etf.code}' is already used by {ETFS[etf.code].isin}; pick another code.")
    ETFS[etf.code] = etf
    _BY_ISIN[etf.isin] = etf.code
    return etf


def code_for_isin(isin: str) -> str | None:
    return _BY_ISIN.get(isin.strip().upper())


def resolve_code(key: str) -> str:
    """ETF code for a code or an ISIN (case-insensitive)."""
    k = key.strip().upper()
    if k in ETFS:
        return k
    if k in _BY_ISIN:
        return _BY_ISIN[k]
    raise ValueError(f"Unknown ETF '{key}'. Known codes: {', '.join(ETFS)}. "
                     f"To add one from Curvo: portfolio-data add {key}")


def normalize_alloc(alloc: Allocation) -> dict[str, float]:
    """Validate an allocation and return it as {code: percent} in registry order, non-zero weights only.

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
    return {c: out[c] for c in ETFS if out.get(c, 0) > 0}


def parse_alloc_args(items: Sequence[str]) -> dict[str, float]:
    """Parse command-line entries like ``["WORLD=60", "BONDS=40"]`` (not yet validated)."""
    alloc: dict[str, float] = {}
    for item in items:
        key, _, pct = item.partition("=")
        if not pct:
            raise ValueError(f"Bad allocation entry '{item}'. Use CODE=percent, codes: {', '.join(ETFS)}")
        alloc[key.strip()] = alloc.get(key.strip(), 0.0) + float(pct)
    return alloc
