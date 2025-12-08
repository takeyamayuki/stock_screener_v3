"""US 52-week high screener using Alpha Vantage data."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

# Ensure project root is on sys.path when run as a script
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import screener as base  # noqa: E402
from scripts.providers.alpha_vantage_us import AlphaVantageUS  # noqa: E402

JST_TODAY = base.TODAY
REPORT_DIR = "reports/us"
base.SYMBOLS_PATH = "config/symbols_us.txt"
base.REPORT_CSV = f"{REPORT_DIR}/screen_us_{JST_TODAY}.csv"
base.REPORT_MD = f"{REPORT_DIR}/screen_us_{JST_TODAY}.md"
base.FinancialDataProvider = AlphaVantageUS  # type: ignore
base.ALLOW_EMPTY_FINANCIALS = True
os.makedirs(REPORT_DIR, exist_ok=True)


def main():
    base.main()


if __name__ == "__main__":
    main()
