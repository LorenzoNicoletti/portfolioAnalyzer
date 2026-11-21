"""Fetch monthly EUR series from Curvo Backtest and keep the data workbook up to date.

Curvo publishes its data through an MCP server at https://curvo.eu/backtest/mcp (no key needed).
It is called with the official ``mcp`` Python SDK, using two tools:

    search      a name, ISIN or ticker  -> matching funds (id = ISIN, tickers, first and last month)
    get_series  id + currency           -> one value per month, plus fund details and disclosures

    add_etfs(["EUNL", "SXR8=SP500B"])   add ETFs by ticker or ISIN, optionally with your own code
    update_all()                        create the workbook with the built-in ETFs, or refresh every series

Both write the workbook described in data.py; the command line for them is ``portfolio-data``.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path

import pandas as pd

from .data import INFO_COLUMNS, data_path, read_workbook, write_workbook
from . import etfs as registry
from .etfs import BUILTIN_ETFS, code_for_isin

CURVO_MCP_URL = "https://curvo.eu/backtest/mcp"
CURRENCY = "EUR"
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
CODE_RE = re.compile(r"^[A-Z0-9_.-]{1,20}$")

NOTES = [
    "Source: Curvo Backtest (curvo.eu/backtest) via its MCP server, retrieved {date}. Monthly values in EUR.",
    "Values are simulated from each fund's tracked index minus its TER (not the fund's actual traded price), "
    "so they are index-level values, not the euro share price you see at your broker. "
    "Use them for returns, not absolute price.",
    "They ignore the rest of each fund's tracking difference, such as trading costs and securities lending income.",
    "Past performance does not guarantee future results. Investing involves risk, including loss of capital.",
]

Fetcher = Callable[[Sequence[str]], list[dict]]  # queries -> one get_series response per query


class CurvoError(Exception):
    """A query matched no fund or several funds, or Curvo returned an error."""


# ---------------------------------------------------------------------- MCP --
def pick_fund(query: str, results: list[dict]) -> dict:
    """The one fund in Curvo search results that matches query by ISIN or ticker exactly."""
    q = query.strip().upper()
    funds = [r for r in results if r.get("kind") == "fund"]
    hits = [f for f in funds if f["id"].upper() == q] or \
           [f for f in funds if q in (t.upper() for t in f.get("tickers", []))]
    if len(hits) == 1:
        return hits[0]
    shown = "\n".join(f"    {f['id']}  {f['name']}  (tickers: {', '.join(f.get('tickers', []))})"
                      for f in (hits or funds)[:10]) or "    (nothing found)"
    why = "matches several funds" if hits else "matches no fund by ticker or ISIN"
    raise CurvoError(f"'{query}' {why} on Curvo. Use the ISIN instead. Candidates:\n{shown}")


async def _call(session, tool: str, args: dict) -> dict:
    res = await session.call_tool(tool, args)
    text = res.content[0].text if res.content else ""
    if res.isError:
        raise CurvoError(f"Curvo {tool} {args} failed: {text}")
    return res.structuredContent or json.loads(text)


async def _fetch(queries: Sequence[str]) -> list[dict]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    out: list[dict] = []
    error: Exception | None = None
    async with streamablehttp_client(CURVO_MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            try:
                for q in queries:
                    q = q.strip().upper()
                    fund_id = q if ISIN_RE.match(q) else pick_fund(q, (await _call(session, "search", {"query": q}))["results"])["id"]
                    out.append(await _call(session, "get_series", {"id": fund_id, "currency": CURRENCY}))
            except CurvoError as e:
                error = e  # re-raised outside the MCP task groups, so it is not wrapped in an ExceptionGroup
    if error:
        raise error
    return out


def fetch_funds(queries: Sequence[str]) -> list[dict]:
    """get_series response (EUR) for each query (ticker or ISIN), over one MCP session."""
    return asyncio.run(_fetch(list(queries))) if queries else []


def series_of(fund: dict) -> pd.Series:
    """Monthly values of a get_series response, indexed by month start."""
    months, values = zip(*fund["points"])
    return pd.Series(values, index=pd.to_datetime(list(months), format="%Y-%m"), dtype=float, name=fund["id"])


def info_row(fund: dict, code: str, today: str) -> dict:
    """The Fund info sheet row of a get_series response."""
    dividends = next((d.split(":", 1)[1].strip() for d in fund.get("disclosures", [])
                      if d.lower().startswith("dividends:")), None)
    return {
        "Code": code, "Fund": fund["name"], "Tickers": ", ".join(fund.get("tickers", [])),
        "Tracked index": (fund.get("trackedIndex") or {}).get("name"),
        "TER %": fund.get("totalExpenseRatioPercent"), "Fund inception": fund.get("inceptionDate"),
        "Series start": fund.get("firstMonth"), "Series end": fund.get("lastMonth"),
        "Dividends": dividends[:1].upper() + dividends[1:] if dividends else None,
        "Curvo Backtest link": fund.get("url", "").split("?")[0], "Retrieved": today,
    }


# ----------------------------------------------------------------- workbook --
def _read(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    if path.is_file():
        return read_workbook(path)
    return pd.DataFrame(index=pd.DatetimeIndex([], name="Month")), pd.DataFrame(columns=INFO_COLUMNS).set_index("ISIN")


def _merge(prices: pd.DataFrame, info: pd.DataFrame, funds: list[dict], codes: list[str]):
    today = date.today().isoformat()
    for fund, code in zip(funds, codes):
        isin = fund["id"].upper()
        prices = prices.drop(columns=isin, errors="ignore").join(series_of(fund).rename(isin), how="outer")
        for col, value in info_row(fund, code, today).items():
            if col not in info.columns:
                info[col] = None
            info.loc[isin, col] = value  # other columns of an existing row (e.g. your own) are kept
    prices.index.name = "Month"
    return prices, info


def _save(path: Path, prices: pd.DataFrame, info: pd.DataFrame) -> None:
    today = date.today().isoformat()
    write_workbook(path, prices, info, [n.format(date=today) for n in NOTES])


def parse_add_args(items: Sequence[str]) -> list[tuple[str, str | None]]:
    """["EUNL", "SXR8=SP500B"] -> [("EUNL", None), ("SXR8", "SP500B")]"""
    out = []
    for item in items:
        query, _, code = item.partition("=")
        code = code.strip().upper() or None
        if code and not CODE_RE.match(code):
            raise ValueError(f"Bad code '{code}': use letters, digits, '_', '-' or '.' (max 20).")
        out.append((query.strip().upper(), code))
    return out


def add_etfs(items: Sequence[tuple[str, str | None]], path: str | Path | None = None,
             fetch: Fetcher = fetch_funds) -> list[tuple[str, str]]:
    """Add ETFs (ticker or ISIN, optional code) to the workbook; returns [(code, ISIN)] of those added.

    The code defaults to the ticker given, or to the fund's first ticker when an ISIN is given.
    ETFs already in the workbook are skipped (use update_all to refresh them).
    """
    path = data_path(path, must_exist=False)
    prices, info = _read(path)
    used = {str(c).upper(): isin for isin, c in info.get("Code", pd.Series(dtype=object)).items() if pd.notna(c)}
    used |= {e.code: e.isin for e in registry.ETFS.values()}

    funds = fetch([q for q, _ in items])
    new_funds, codes = [], []
    for (query, code), fund in zip(items, funds):
        isin = fund["id"].upper()
        if isin in prices.columns:
            print(f"  {query}: {isin} is already in the data as {info.get('Code', {}).get(isin, isin)}, skipped")
            continue
        code = code or code_for_isin(isin) or (query if not ISIN_RE.match(query) else
                                               (fund.get("tickers") or [isin])[0].upper())
        if used.get(code, isin) != isin:
            raise ValueError(f"Code '{code}' is already used by {used[code]}. Give another one: {query}=MYCODE")
        used[code] = isin
        new_funds.append(fund)
        codes.append(code)
    if new_funds:
        _save(path, *_merge(prices, info, new_funds, codes))
    return [(c, f["id"]) for c, f in zip(codes, new_funds)]


def update_all(path: str | Path | None = None, fetch: Fetcher = fetch_funds) -> list[str]:
    """Download every series in the workbook again (new months, corrections) and save it.

    If the workbook does not exist yet, it is created with the built-in ETFs. Returns the ISINs fetched.
    """
    path = data_path(path, must_exist=False)
    prices, info = _read(path)
    isins = list(prices.columns) or [e.isin for e in BUILTIN_ETFS]
    codes = []
    for isin in isins:
        stored = info["Code"].get(isin) if "Code" in info.columns and isin in info.index else None
        codes.append(str(stored) if pd.notna(stored) and stored else code_for_isin(isin) or isin)
    funds = fetch(isins)
    _save(path, *_merge(prices, info, funds, codes))
    return isins
