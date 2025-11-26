"""Fetch US tickers that hit 52-week highs from Kabutan US and save to config/symbols_us.txt."""
from __future__ import annotations

import os
from pathlib import Path
from typing import List

import requests
from bs4 import BeautifulSoup

TARGET_URL = "https://us.kabutan.jp/warnings/record_w52_high_price"
OUTPUT_PATH = Path("config/symbols_us.txt")


def fetch_symbols() -> List[str]:
    resp = requests.get(TARGET_URL, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    tickers: List[str] = []
    rows = soup.select("table tr")
    for tr in rows[1:]:  # skip header
        tds = tr.find_all("td")
        if not tds:
            continue
        ticker = tds[0].get_text(strip=True)
        if ticker:
            tickers.append(ticker)
    return tickers


def main() -> None:
    symbols = fetch_symbols()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n".join(symbols) + ("\n" if symbols else ""), encoding="utf-8")
    print(f"Saved {len(symbols)} symbols to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
