import numpy as np
import pandas as pd
import pytest

from portfolio_backtest.engine import REBALANCE_MONTHS, metrics, perform_backtest, simulate_values


def backtest(invest, alloc, start=None, end=None, prices=None):
    """One portfolio {ticker: %}; returns its monthly values as a Series."""
    r = perform_backtest(invest, list(alloc), [list(alloc.values())], start, end, keep_values=True, prices=prices)
    return pd.Series(r.values[:, 0], index=r.dates), r


def loop_values(invest, w, prices, every):
    """Reference implementation: step month by month, rebalance every `every` months."""
    units = invest * w / prices[0]
    out = [invest]
    for t in range(1, len(prices)):
        v = float(units @ prices[t])
        out.append(v)
        if every and t % every == 0:
            units = v * w / prices[t]
    return np.array(out)


@pytest.mark.parametrize("every", list(REBALANCE_MONTHS.values()))
def test_vectorised_matches_loop(prices, every):
    px = prices.to_numpy()
    w = np.array([0.10, 0.30, 0.15, 0.25, 0.05, 0.15])
    got = simulate_values(10_000, w[None, :], px, every)[:, 0]
    np.testing.assert_allclose(got, loop_values(10_000, w, px, every), rtol=1e-12)


def test_many_portfolios_match_single_runs(prices):
    allocs = np.array([[60, 40, 0], [0, 50, 50], [100, 0, 0]])
    etfs = ["UETW", "SXRQ", "PPFB"]
    many = perform_backtest(10_000, etfs, allocs, prices=prices)
    for k, row in enumerate(allocs):
        held = {e: w for e, w in zip(etfs, row) if w > 0}
        _, one = backtest(10_000, held, start="2006-12", prices=prices)
        assert one.final_value[0] == pytest.approx(many.final_value[k], rel=1e-12)
        assert one.volatility[0] == pytest.approx(many.volatility[k], rel=1e-12)


def test_single_etf_follows_its_price(prices):
    values, _ = backtest(1_000, {"PPFB": 100}, prices=prices)
    expected = 1_000 * prices["PPFB"] / prices["PPFB"].iloc[0]
    np.testing.assert_allclose(values.to_numpy(), expected.to_numpy(), rtol=1e-12)


def test_metrics_on_known_series():
    values = 100 * 1.01 ** np.arange(25)[:, None]  # +1 % every month for 2 years
    cagr, vol, mdd = metrics(values)
    assert cagr[0] == pytest.approx(1.01 ** 12 - 1)
    assert vol[0] == pytest.approx(0, abs=1e-12)
    assert mdd[0] == 0

    dip = np.array([[100.0], [80.0], [120.0], [90.0]])
    assert metrics(dip)[2][0] == pytest.approx(-0.25)


def test_window_and_isin_input(prices):
    values, _ = backtest(10_000, {"IE00BD4TXV59": 100}, start="2010-01", end="2015-12", prices=prices)
    assert values.index[0] == pd.Timestamp("2010-01-01")
    assert values.index[-1] == pd.Timestamp("2015-12-01")


@pytest.mark.parametrize("kwargs, msg", [
    (dict(etfs=["UETW"], allocs=[[90]]), "sum to 100"),
    (dict(etfs=["UETW", "PPFB"], allocs=[[110, -10]]), "Negative"),
    (dict(etfs=["UETW"], allocs=[[50, 50]]), "columns"),
    (dict(etfs=["NOPE"], allocs=[[100]]), "Unknown ETF"),
    (dict(etfs=["UETW"], allocs=[[100]], rebalance="weekly"), "Unknown rebalance"),
])
def test_invalid_input(prices, kwargs, msg):
    with pytest.raises(ValueError, match=msg):
        perform_backtest(10_000, prices=prices, **kwargs)


def test_missing_data_at_start(prices):
    p = prices.copy()
    p.loc[:"2008-01-01", "AEME"] = np.nan
    with pytest.raises(ValueError, match="No data"):
        backtest(10_000, {"AEME": 50, "UETW": 50}, start="2006-12", prices=p)
    values, _ = backtest(10_000, {"AEME": 50, "UETW": 50}, prices=p)  # default start: first month AEME has data
    assert values.index[0] == pd.Timestamp("2008-02-01")
    backtest(10_000, {"UETW": 100}, start="2006-12", prices=p)  # unheld NaN column is fine


def test_default_start_is_first_common_month(prices):
    p = prices.copy()
    p.loc[:"2009-12-01", "PPFB"] = np.nan
    assert backtest(10_000, {"UETW": 100}, prices=p)[0].index[0] == pd.Timestamp("2006-12-01")
    assert backtest(10_000, {"UETW": 50, "PPFB": 50}, prices=p)[0].index[0] == pd.Timestamp("2010-01-01")
