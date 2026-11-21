import numpy as np
import pandas as pd
import pytest

from portfolio_backtest.etfs import BUILTIN_ETFS

TICKERS = [e.ticker for e in BUILTIN_ETFS]


@pytest.fixture
def prices() -> pd.DataFrame:
    """Synthetic monthly prices for all ETFs: 20 years of random walks, so no data file is needed."""
    rng = np.random.default_rng(0)
    idx = pd.date_range("2006-12-01", periods=240, freq="MS")
    rets = rng.normal(0.006, 0.04, size=(len(idx), len(TICKERS)))
    rets[0] = 0
    return pd.DataFrame(100 * np.cumprod(1 + rets, axis=0), index=idx, columns=TICKERS)
