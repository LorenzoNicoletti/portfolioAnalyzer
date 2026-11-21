"""Curvo fetching and the data workbook, with a fake Curvo client (no network)."""

import pandas as pd
import pytest

from portfolio_backtest import etfs as etfs_mod
from portfolio_backtest.curvo import CurvoError, add_etfs, parse_add_args, pick_fund, update_all
from portfolio_backtest.data import clear_cache, load_prices, read_workbook
from portfolio_backtest.engine import perform_backtest
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
    by_isin = {e.isin: fake_fund(e.isin, [e.ticker]) for e in BUILTIN_ETFS}
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
def workbook(tmp_path):
    """Empty data location; the ETF registry is restored after the test."""
    saved = dict(etfs_mod.ETFS), dict(etfs_mod._BY_ISIN)
    clear_cache()
    yield tmp_path / "data.xlsx"
    clear_cache()
    for live, before in zip((etfs_mod.ETFS, etfs_mod._BY_ISIN), saved):  # same objects, old contents
        live.clear()
        live.update(before)


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
    assert parse_add_args(["eunl", "IE00B5BMR087=sxr8"]) == [("EUNL", None), ("IE00B5BMR087", "SXR8")]
    with pytest.raises(ValueError, match="Bad ticker"):
        parse_add_args(["IE00B5BMR087=bad ticker"])


def test_update_creates_workbook_with_builtin_etfs(workbook):
    update_all(workbook, fetch=fake_fetch)
    prices, info = read_workbook(workbook)
    assert list(prices.columns) == [e.isin for e in BUILTIN_ETFS]
    assert list(info["Ticker"]) == [e.ticker for e in BUILTIN_ETFS]
    assert list(load_prices(workbook).columns) == [e.ticker for e in BUILTIN_ETFS]


def test_add_etf_extends_workbook_and_is_usable(workbook):
    update_all(workbook, fetch=fake_fetch)
    added = add_etfs(parse_add_args(["EUNL"]), workbook, fetch=fake_fetch)
    assert added == [("EUNL", "IE00B4L5Y983")]

    prices = load_prices(workbook)
    assert list(prices.columns)[-1] == "EUNL"
    assert prices["EUNL"].first_valid_index() == pd.Timestamp("2001-01-01")
    r = perform_backtest(10_000, ["EUNL", "UETW"], [[50, 50]], prices=prices)  # new ticker works
    assert r.dates[0] == pd.Timestamp("2001-01-01")                                # first month both have data

    # adding it again is a no-op; the ticker of another ETF cannot be taken
    assert add_etfs(parse_add_args(["EUNL"]), workbook, fetch=fake_fetch) == []
    EXTRA["SXR8"] = fake_fund("IE00B5BMR087", ["SXR8"])
    try:
        with pytest.raises(ValueError, match="already used"):
            add_etfs(parse_add_args(["SXR8=UETW"]), workbook, fetch=fake_fetch)
    finally:
        del EXTRA["SXR8"]


def test_update_keeps_tickers_and_extra_columns(workbook):
    update_all(workbook, fetch=fake_fetch)
    add_etfs([("IE00B4L5Y983", "IWDA")], workbook, fetch=fake_fetch)  # by ISIN, choosing its ticker
    prices, info = read_workbook(workbook)
    info["My note"] = "keep me"
    from portfolio_backtest.data import write_workbook
    write_workbook(workbook, prices, info)

    update_all(workbook, fetch=fake_fetch)
    prices, info = read_workbook(workbook)
    assert info.loc["IE00B4L5Y983", "Ticker"] == "IWDA"
    assert (info["My note"] == "keep me").all()
    assert len(prices.columns) == len(BUILTIN_ETFS) + 1


# ------------------------------------------------------------ PortfolioAnalyzer + command line --
def test_analyzer_backtest_sobol_and_list(workbook):
    from portfolio_backtest import DEFAULT_ALLOC, PortfolioAnalyzer

    update_all(workbook, fetch=fake_fetch)
    add_etfs([("EUNL", None)], workbook, fetch=fake_fetch)
    pa = PortfolioAnalyzer(data=workbook)

    r = pa.backtest(report=False, plot=False)  # row 0 = the allocation, then each held ETF alone
    assert r.etfs == list(DEFAULT_ALLOC) and len(r.allocs) == 1 + len(DEFAULT_ALLOC)
    direct = perform_backtest(pa.invest, list(DEFAULT_ALLOC), [list(DEFAULT_ALLOC.values())], prices=pa.prices)
    assert r.final_value[0] == pytest.approx(direct.final_value[0], rel=1e-12)

    pa.alloc = {"EUNL": 70, "SXRQ": 30}  # settings are plain attributes
    s = pa.sobol(["EUNL", "SXRQ", "PPFB"], n_samples=64, plot=False)
    assert s.etfs == ["EUNL", "SXRQ", "PPFB"] and len(s.allocs) == 64 + 3

    etfs = pa.list_etfs()
    assert list(etfs.index)[-1] == "EUNL"
    assert etfs.loc["EUNL", "isin"] == "IE00B4L5Y983" and etfs.loc["UETW", "isin"] == "IE00BD4TXV59"


def test_command_line(workbook, capsys):
    from portfolio_backtest.cli import main

    update_all(workbook, fetch=fake_fetch)
    main(["data", "list", "--data", str(workbook)])
    assert "UETW" in capsys.readouterr().out
    main(["backtest", "--no-plot", "--alloc", "UETW=60", "SXRQ=40", "--data", str(workbook)])
    out = capsys.readouterr().out
    assert "Portfolio" in out and "UETW 60%" in out
    with pytest.raises(SystemExit, match="sum to 90"):
        main(["backtest", "--no-plot", "--alloc", "UETW=90", "--data", str(workbook)])


def test_old_workbook_with_code_column(workbook):
    from portfolio_backtest.data import write_workbook

    update_all(workbook, fetch=fake_fetch)
    add_etfs([("EUNL", None)], workbook, fetch=fake_fetch)
    prices, info = read_workbook(workbook)
    info = info.rename(columns={"Ticker": "Code"})          # the old layout
    info.loc["IE00B4L5Y983", "Code"] = "MYWORLD"            # an old self-made code, not a ticker
    write_workbook(workbook, prices, info)
    clear_cache()
    etfs_mod.ETFS.pop("EUNL", None)
    etfs_mod._BY_ISIN.pop("IE00B4L5Y983", None)

    assert list(load_prices(workbook).columns)[-1] == "EUNL"  # first Curvo ticker of the fund
    update_all(workbook, fetch=fake_fetch)                    # rewrites it in the new layout
    _, info = read_workbook(workbook)
    assert "Code" not in info.columns and info.loc["IE00B4L5Y983", "Ticker"] == "EUNL"
