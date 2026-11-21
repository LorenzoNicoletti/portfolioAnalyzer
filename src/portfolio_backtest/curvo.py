"""Fetch monthly EUR series from Curvo Backtest and keep the data workbook up to date.

Curvo publishes its data through an MCP server at https://curvo.eu/backtest/mcp (no key needed).
It is called with the official ``mcp`` Python SDK, using two tools:

    search      a name, ISIN or ticker  -> matching funds (id = ISIN, tickers, first and last month)
    get_series  id + currency           -> one value per month, plus fund details and disclosures

    add_etfs([("EUNL", None)])          add ETFs by ticker or ISIN (an ISIN gets the fund's first ticker,
                                        or the one given: ("IE00B5BMR087", "SXR8"))
    update_all()                        create the workbook with the built-in ETFs, or refresh every series

Both write the workbook described in data.py; use them through PortfolioAnalyzer.update_data / add_etfs
or ``portfolio data update`` / ``portfolio data add``.
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
from .etfs import BUILTIN_ETFS, ticker_for_isin

CURVO_MCP_URL = "https://curvo.eu/backtest/mcp"
CURRENCY = "EUR"
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
TICKER_RE = re.compile(r"^[A-Z0-9_.-]{1,20}$")

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


def info_row(fund: dict, ticker: str, today: str) -> dict:
    """The Fund info sheet row of a get_series response."""
    dividends = next((d.split(":", 1)[1].strip() for d in fund.get("disclosures", [])
                      if d.lower().startswith("dividends:")), None)
    return {
        "Ticker": ticker, "Fund": fund["name"], "Tickers": ", ".join(fund.get("tickers", [])),
        "Tracked index": (fund.get("trackedIndex") or {}).get("name"),
        "TER %": fund.get("totalExpenseRatioPercent"), "Fund inception": fund.get("inceptionDate"),
        "Series start": fund.get("firstMonth"), "Series end": fund.get("lastMonth"),
        "Dividends": dividends[:1].upper() + dividends[1:] if dividends else None,
        "Curvo Backtest link": fund.get("url", "").split("?")[0], "Retrieved": today,
    }


# ----------------------------------------------------------------- workbook --
def _read(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not path.is_file():
        return pd.DataFrame(index=pd.DatetimeIndex([], name="Month")), pd.DataFrame(columns=INFO_COLUMNS).set_index("ISIN")
    prices, info = read_workbook(path)
    return prices, info.drop(columns="Code", errors="ignore")  # "Code" of older workbooks, replaced by "Ticker"


def _stored_tickers(info: pd.DataFrame) -> dict[str, str]:
    """{ISIN: ticker} from the Ticker column."""
    col = info["Ticker"] if "Ticker" in info.columns else pd.Series(dtype=object)
    return {isin: str(t).strip().upper() for isin, t in col.items() if pd.notna(t) and str(t).strip()}


def _merge(prices: pd.DataFrame, info: pd.DataFrame, funds: list[dict], tickers: list[str]):
    today = date.today().isoformat()
    for fund, ticker in zip(funds, tickers):
        isin = fund["id"].upper()
        prices = prices.drop(columns=isin, errors="ignore").join(series_of(fund).rename(isin), how="outer")
        for col, value in info_row(fund, ticker, today).items():
            if col not in info.columns:
                info[col] = None
            info.loc[isin, col] = value  # other columns of an existing row (e.g. your own) are kept
    prices.index.name = "Month"
    return prices, info


def _save(path: Path, prices: pd.DataFrame, info: pd.DataFrame) -> None:
    write_workbook(path, prices, info, [n.format(date=date.today().isoformat()) for n in NOTES])


def parse_add_args(items: Sequence[str]) -> list[tuple[str, str | None]]:
    """["EUNL", "IE00B5BMR087=SXR8"] -> [("EUNL", None), ("IE00B5BMR087", "SXR8")]"""
    out = []
    for item in items:
        query, _, ticker = item.partition("=")
        ticker = ticker.strip().upper() or None
        if ticker and not TICKER_RE.match(ticker):
            raise ValueError(f"Bad ticker '{ticker}': use letters, digits, '_', '-' or '.' (max 20).")
        out.append((query.strip().upper(), ticker))
    return out


def add_etfs(items: Sequence[tuple[str, str | None]], path: str | Path | None = None,
             fetch: Fetcher = fetch_funds) -> list[tuple[str, str]]:
    """Add ETFs (ticker or ISIN, optional ticker to use) to the workbook; returns [(ticker, ISIN)] of those added.

    The ticker is the one searched for; for an ISIN, the one given or else the fund's first Curvo ticker.
    ETFs already in the workbook are skipped (use update_all to refresh them).
    """
    path = data_path(path, must_exist=False)
    prices, info = _read(path)
    stored = _stored_tickers(info)
    used = {t: isin for isin, t in stored.items()} | {e.ticker: e.isin for e in registry.ETFS.values()}

    funds = fetch([q for q, _ in items])
    new_funds, tickers = [], []
    for (query, ticker), fund in zip(items, funds):
        isin = fund["id"].upper()
        if isin in prices.columns:
            print(f"  {query}: {isin} is already in the data as {stored.get(isin, isin)}, skipped")
            continue
        ticker = ticker or ticker_for_isin(isin) or (query if not ISIN_RE.match(query) else
                                                     (fund.get("tickers") or [isin])[0].upper())
        if used.get(ticker, isin) != isin:
            raise ValueError(f"Ticker '{ticker}' is already used by {used[ticker]}. "
                             f"Choose another of the fund's tickers: {query}=TICKER")
        used[ticker] = isin
        new_funds.append(fund)
        tickers.append(ticker)
    if new_funds:
        _save(path, *_merge(prices, info, new_funds, tickers))
    return [(t, f["id"]) for t, f in zip(tickers, new_funds)]


def update_all(path: str | Path | None = None, fetch: Fetcher = fetch_funds) -> list[str]:
    """Download every series in the workbook again (new months, corrections) and save it.

    If the workbook does not exist yet, it is created with the built-in ETFs. Returns the ISINs fetched.
    """
    path = data_path(path, must_exist=False)
    prices, info = _read(path)
    isins = list(prices.columns) or [e.isin for e in BUILTIN_ETFS]
    stored = _stored_tickers(info)
    funds = fetch(isins)
    tickers = [ticker_for_isin(isin) or stored.get(isin) or (f.get("tickers") or [isin])[0].upper()
               for isin, f in zip(isins, funds)]
    _save(path, *_merge(prices, info, funds, tickers))
    return isins
