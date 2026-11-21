"""Main script: edit the settings below, then run

    python main.py          (or Run / F5 in VS Code)

It updates the data if asked (or if there is none yet), adds ETFs, runs the backtest and opens the
Sobol study. The backtest chart opens first; close it to continue with the Sobol study.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))  # works without "pip install -e ." too

from portfolio_backtest import PortfolioAnalyzer  # noqa: E402
from portfolio_backtest.data import data_path  # noqa: E402

# ------------------------------------------------------------------ settings --
ALLOC = None              # None = basis allocation (AEME 13, UETW 25, VUAA 10, SXRQ 20, PPFB 10, LYP6 22)
                          # or e.g. {"UETW": 60, "SXRQ": 30, "PPFB": 10}
INVEST = 10_000           # EUR
START, END = None, None   # "YYYY-MM"; None = first / last month in which all ETFs have data
REBALANCE = "annual"      # none, monthly, quarterly, semiannual, annual

UPDATE_DATA = False       # True: download the latest months from Curvo first
ADD_ETFS = []             # ETFs to add from Curvo by ticker or ISIN, e.g. ["EUNL", "IE00B5BMR087=SXR8"]

RUN_BACKTEST = True
RUN_SOBOL = True
SOBOL_ETFS = ["AEME", "UETW", "SXRQ", "PPFB", "LYP6"]    # tickers spanned by the Sobol study
SOBOL_SAMPLES = 8192
SOBOL_FILTERS = {}        # filters active when the chart opens, e.g. {"PPFB": (10, 30)}


# ---------------------------------------------------------------------- run --
if __name__ == "__main__":
    pa = PortfolioAnalyzer(ALLOC, INVEST, START, END, REBALANCE)

    if UPDATE_DATA or not data_path(must_exist=False).is_file():
        pa.update_data()
    if ADD_ETFS:
        pa.add_etfs(*ADD_ETFS)
    print(f"\n{pa.list_etfs().to_string()}\n")

    if RUN_BACKTEST:
        pa.backtest()
    if RUN_SOBOL:
        pa.sobol(SOBOL_ETFS, SOBOL_SAMPLES, filters=SOBOL_FILTERS)
