import numpy as np
import pytest

from portfolio_backtest.etfs import CODES, normalize_alloc, parse_alloc_args, resolve_code
from portfolio_backtest.sobol import run_study, sobol_allocations
from portfolio_backtest.sobol.cli import parse_filters


def test_normalize_alloc_dict_isin_and_order():
    out = normalize_alloc({"gold": 10, "IE00BD4TXV59": 60, "WORLD": 20, "BONDS": 10, "EM": 0})
    assert out == {"WORLD": 80, "BONDS": 10, "GOLD": 10}
    assert list(out) == [c for c in CODES if c in out]


def test_normalize_alloc_sequence():
    assert normalize_alloc([0, 50, 0, 50, 0, 0]) == {"WORLD": 50, "BONDS": 50}
    with pytest.raises(ValueError, match="Need 6"):
        normalize_alloc([50, 50])


def test_parse_alloc_args():
    assert parse_alloc_args(["WORLD=60", "BONDS=40"]) == {"WORLD": 60, "BONDS": 40}
    with pytest.raises(ValueError, match="CODE=percent"):
        parse_alloc_args(["WORLD"])


def test_resolve_code():
    assert resolve_code(" sp500 ") == "SP500"
    with pytest.raises(ValueError):
        resolve_code("XYZ")


def test_parse_filters():
    assert parse_filters(["gold=25-100"]) == {"GOLD": (25.0, 100.0)}
    with pytest.raises(ValueError):
        parse_filters(["GOLD=25"])


def test_sobol_allocations_sum_to_100_and_reproducible():
    a = sobol_allocations(256, 4, seed=1)
    assert a.shape == (256, 4)
    np.testing.assert_allclose(a.sum(axis=1), 100)
    assert (a >= 0).all()
    np.testing.assert_array_equal(a, sobol_allocations(256, 4, seed=1))


def test_run_study(prices):
    s = run_study(["WORLD", "BONDS", "GOLD"], n_samples=128, prices=prices)
    assert len(s.allocs) == 128 + 3
    np.testing.assert_allclose(s.allocs[s.singles], 100 * np.eye(3))
    assert set(s.picks()) == {"Highest CAGR", "Lowest volatility", "Best CAGR / volatility"}
