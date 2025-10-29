import os
import re
import sys
from typing import Dict, Iterable, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

# --- 環境変数 ---
MAX_SYMBOLS = int(os.environ.get("MAX_SYMBOLS", "200"))
TARGET_PER_MARKET = int(os.environ.get("TARGET_PER_MARKET", "20"))

# --- パス ---
os.makedirs("config", exist_ok=True)
SYMBOLS_PATH = "config/symbols.txt"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
)

KABUTAN_URL = "https://kabutan.jp/warning/record_w52_high_price/"

MARKET_ABBR_TO_NAME = {
    "東Ｐ": "プライム",
    "東Ｓ": "スタンダード",
    "東Ｇ": "グロース",
}
TARGET_MARKETS = tuple(MARKET_ABBR_TO_NAME.values())
KABUTAN_MARKET_PARAMS = {
    "プライム": {"market": "1"},
    "スタンダード": {"market": "2"},
    "グロース": {"market": "3"},
}


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def iter_kabutan_candidates(
    market: str,
    max_pages: int = 60,
) -> Iterable[Tuple[str, Optional[str]]]:
    base_params = KABUTAN_MARKET_PARAMS.get(market, {})
    for page in range(1, max_pages + 1):
        try:
            params = dict(base_params)
            if page > 1:
                params["page"] = page
            resp = requests.get(
                KABUTAN_URL,
                params=params or {"page": page},
                headers={"User-Agent": USER_AGENT},
                timeout=30,
            )
            if resp.status_code == 404:
                break
            resp.raise_for_status()
        except Exception as exc:
            log(f"[fetch][kabutan] page {page} failed: {exc}")
            break
        soup = BeautifulSoup(resp.text, "lxml")
        rows = soup.select("table.stock_table tbody tr")
        if not rows:
            break
        for tr in rows:
            cells = tr.find_all("td")
            if not cells:
                continue
            code = cells[0].get_text(strip=True).upper()
            market_raw = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            if not re.fullmatch(r"\d{3}[0-9A-Z]", code):
                continue
            normalized_market = MARKET_ABBR_TO_NAME.get(market_raw)
            yield code, normalized_market or market


def add_codes(
    collected: Dict[str, List[str]],
    codes_with_market: Iterable[Tuple[str, Optional[str]]],
) -> None:
    for code, market in codes_with_market:
        if market not in TARGET_MARKETS:
            continue
        bucket = collected[market]
        if len(bucket) >= TARGET_PER_MARKET:
            continue
        if code in bucket:
            continue
        bucket.append(code)


def flatten_symbols(collected: Dict[str, List[str]]) -> List[str]:
    ordered = []
    for market in TARGET_MARKETS:
        ordered.extend(collected[market][:TARGET_PER_MARKET])
    return [f"{code}.T" for code in ordered]


def main() -> None:
    collected: Dict[str, List[str]] = {market: [] for market in TARGET_MARKETS}

    for market in TARGET_MARKETS:
        add_codes(collected, iter_kabutan_candidates(market=market, max_pages=60))

    totals = {market: len(codes) for market, codes in collected.items()}
    for market, count in totals.items():
        if count < TARGET_PER_MARKET:
            log(f"[fetch] {market} は {count} 件しか取得できませんでした。")

    symbols = flatten_symbols(collected)
    if MAX_SYMBOLS:
        symbols = symbols[:MAX_SYMBOLS]

    with open(SYMBOLS_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(symbols) + ("\n" if symbols else ""))
    log(f"[fetch] {len(symbols)} symbols written to {SYMBOLS_PATH}")


if __name__ == "__main__":
    main()
