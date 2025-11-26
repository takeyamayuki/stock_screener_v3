"""US 52-week high screener using Alpha Vantage data."""
from __future__ import annotations

import os

import pandas as pd

from scripts import screener as base
from scripts.providers.alpha_vantage_us import AlphaVantageUS

JST_TODAY = base.TODAY
REPORT_DIR = "reports/us"
base.SYMBOLS_PATH = "config/symbols_us.txt"
base.REPORT_CSV = f"{REPORT_DIR}/screen_us_{JST_TODAY}.csv"
base.REPORT_MD = f"{REPORT_DIR}/screen_us_{JST_TODAY}.md"
base.FinancialDataProvider = AlphaVantageUS  # type: ignore
os.makedirs(REPORT_DIR, exist_ok=True)


def main():
    base.main()


if __name__ == "__main__":
    main()
