import numpy as np
import pytest

from portfolio_backtest.cli import parse_filters
from portfolio_backtest.etfs import ETFS, normalize_alloc, parse_alloc_args, resolve_ticker
from portfolio_backtest.sobol import run_study, sobol_allocations


def test_normalize_alloc_dict_isin_and_order():
    out = normalize_alloc({"ppfb": 10, "IE00BD4TXV59": 60, "UETW": 20, "SXRQ": 10, "AEME": 0})
    assert out == {"UETW": 80, "SXRQ": 10, "PPFB": 10}
    assert list(out) == [c for c in ETFS if c in out]


def test_parse_alloc_args():
    assert parse_alloc_args(["UETW=60", "SXRQ=40"]) == {"UETW": 60, "SXRQ": 40}
    with pytest.raises(ValueError, match="TICKER=percent"):
        parse_alloc_args(["UETW"])


def test_resolve_ticker():
    assert resolve_ticker(" vuaa ") == "VUAA"
    with pytest.raises(ValueError):
        resolve_ticker("XYZ")


def test_parse_filters():
    assert parse_filters(["ppfb=25-100"]) == {"PPFB": (25.0, 100.0)}
    with pytest.raises(ValueError):
        parse_filters(["PPFB=25"])


def test_sobol_allocations_sum_to_100_and_reproducible():
    a = sobol_allocations(256, 4, seed=1)
    assert a.shape == (256, 4)
    np.testing.assert_allclose(a.sum(axis=1), 100)
    assert (a >= 0).all()
    np.testing.assert_array_equal(a, sobol_allocations(256, 4, seed=1))


def test_run_study(prices):
    s = run_study(["UETW", "SXRQ", "PPFB"], n_samples=128, prices=prices)
    assert len(s.allocs) == 128 + 3
    np.testing.assert_allclose(s.allocs[s.singles], 100 * np.eye(3))
    assert set(s.picks()) == {"Highest CAGR", "Lowest volatility", "Best CAGR / volatility"}
