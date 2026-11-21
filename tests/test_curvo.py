"""Curvo fetching and the data workbook, with a fake Curvo client (no network)."""

import pandas as pd
import pytest

from portfolio_backtest import etfs as etfs_mod
from portfolio_backtest.curvo import CurvoError, add_etfs, parse_add_args, pick_fund, update_all
from portfolio_backtest.data import clear_cache, load_prices, read_workbook
from portfolio_backtest.engine import backtest
from portfolio_backtest.etfs import BUILTIN_ETFS


def fake_fund(isin, tickers, first="2000-01", months=48, start_value=100.0, growth=1.01):
    idx = pd.period_range(first, periods=months, freq="M")
    return {
        "kind": "fund", "id": isin, "name": f"Fund {isin}", "tickers": tickers,
        "totalExpenseRatioPercent": 0.2, "trackedIndex": {"name": "Some index"},
        "inceptionDate": "2010-01-01", "firstMonth": str(idx[0]), "lastMonth": str(idx[-1]),
        "url": f"https://curvo.eu/backtest/fund/{isin}?utm_source=mcp",
        "points": [[str(m), start_value * growth ** k] for k, m in enumerate(idx)],
        "disclosures": ["Simulated from ...", "Dividends: net reinvested"],
    }


EXTRA = {"EUNL": fake_fund("IE00B4L5Y983", ["EUNL", "IWDA"], first="2001-01", growth=1.02)}


def fake_fetch(queries):
    by_isin = {e.isin: fake_fund(e.isin, [e.code.lower()]) for e in BUILTIN_ETFS}
    by_isin |= {f["id"]: f for f in EXTRA.values()}
    out = []
    for q in queries:
        q = q.upper()
        if q in EXTRA:
            out.append(EXTRA[q])
        elif q in by_isin:
            out.append(by_isin[q])
        else:
            raise CurvoError(f"'{q}' matches no fund")
    return out


@pytest.fixture
def workbook(tmp_path, monkeypatch):
    """Empty data location; the ETF registry is restored after the test."""
    monkeypatch.setattr(etfs_mod, "ETFS", dict(etfs_mod.ETFS))
    monkeypatch.setattr(etfs_mod, "_BY_ISIN", dict(etfs_mod._BY_ISIN))
    clear_cache()
    yield tmp_path / "data.xlsx"
    clear_cache()


def test_pick_fund_by_ticker_or_isin():
    results = [fake_fund("IE00B4L5Y983", ["EUNL", "IWDA"]), fake_fund("IE00B5BMR087", ["SXR8"]),
               {"kind": "index", "id": "msci-world", "name": "MSCI World"}]
    assert pick_fund("iwda", results)["id"] == "IE00B4L5Y983"
    assert pick_fund("IE00B5BMR087", results)["id"] == "IE00B5BMR087"
    with pytest.raises(CurvoError, match="no fund"):
        pick_fund("MSCI World", results)
    with pytest.raises(CurvoError, match="several"):
        pick_fund("X", [fake_fund("IE0000000001", ["X"]), fake_fund("IE0000000002", ["X"])])


def test_parse_add_args():
    assert parse_add_args(["eunl", "SXR8=sp500b"]) == [("EUNL", None), ("SXR8", "SP500B")]
    with pytest.raises(ValueError, match="Bad code"):
        parse_add_args(["SXR8=bad code"])


def test_update_creates_workbook_with_builtin_etfs(workbook):
    update_all(workbook, fetch=fake_fetch)
    prices, info = read_workbook(workbook)
    assert list(prices.columns) == [e.isin for e in BUILTIN_ETFS]
    assert list(info["Code"]) == [e.code for e in BUILTIN_ETFS]
    assert list(load_prices(workbook).columns) == [e.code for e in BUILTIN_ETFS]


def test_add_etf_extends_workbook_and_is_usable(workbook):
    update_all(workbook, fetch=fake_fetch)
    added = add_etfs(parse_add_args(["EUNL"]), workbook, fetch=fake_fetch)
    assert added == [("EUNL", "IE00B4L5Y983")]

    prices = load_prices(workbook)
    assert list(prices.columns)[-1] == "EUNL"
    assert prices["EUNL"].first_valid_index() == pd.Timestamp("2001-01-01")
    r = backtest(10_000, {"EUNL": 50, "WORLD": 50}, prices=prices)  # new code works in allocations
    assert r.values.index[0] == pd.Timestamp("2001-01-01")         # first month both have data

    # adding it again is a no-op; the code of another ETF cannot be taken
    assert add_etfs(parse_add_args(["EUNL"]), workbook, fetch=fake_fetch) == []
    EXTRA["SXR8"] = fake_fund("IE00B5BMR087", ["SXR8"])
    try:
        with pytest.raises(ValueError, match="already used"):
            add_etfs(parse_add_args(["SXR8=WORLD"]), workbook, fetch=fake_fetch)
    finally:
        del EXTRA["SXR8"]


def test_update_keeps_codes_and_extra_columns(workbook):
    update_all(workbook, fetch=fake_fetch)
    add_etfs([("EUNL", "MYWORLD")], workbook, fetch=fake_fetch)
    prices, info = read_workbook(workbook)
    info["My note"] = "keep me"
    from portfolio_backtest.data import write_workbook
    write_workbook(workbook, prices, info)

    update_all(workbook, fetch=fake_fetch)
    prices, info = read_workbook(workbook)
    assert info.loc["IE00B4L5Y983", "Code"] == "MYWORLD"
    assert (info["My note"] == "keep me").all()
    assert len(prices.columns) == len(BUILTIN_ETFS) + 1
