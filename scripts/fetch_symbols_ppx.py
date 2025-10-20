import os, re, json, sys, time, datetime as dt
import requests
from typing import List

# --- 環境変数 ---
PPX_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
THROTTLE = int(os.environ.get("THROTTLE_SECONDS", "13"))
MAX_SYMBOLS = int(os.environ.get("MAX_SYMBOLS", "200"))

# --- パス ---
os.makedirs("config", exist_ok=True)
os.makedirs("cache", exist_ok=True)
SYMBOLS_PATH = "config/symbols.txt"
CACHE_PATH = "cache/overview.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
)

# --- プロンプト（JSON出力を強制） ---
PROMPTS = [
    # 日本語
    (
        "あなたは日本の株式市場の最新ニュースを参照できます。"
        "「今日（日本時間）の日本株で52週高値を更新した銘柄」のうち、"
        "東証プライム・スタンダード・グロース市場の上場企業のみを対象に、"
        "4桁の証券コードだけを抽出してください。"
        "ETF・ETN・REIT・投資信託・投資法人は除外してください。"
        "出力は **JSONのみ** で、次の形にしてください：\n"
        '{"codes": ["1234", "5678", ...]}\n'
        "JSON以外の文章は一切出力しないでください。"
    ),
    # 英語フォールバック
    (
        "You can browse up-to-date Japanese market news. "
        "List Japanese stocks that hit a 52-week high today (Japan time), "
        "limited to TSE Prime/Standard/Growth listings. Exclude ETFs/ETNs/REITs/funds. "
        "Return **JSON only** in the exact shape: "
        '{"codes": ["1234", "5678", ...]} '
        "Do not output any non-JSON text."
    ),
]

# --- 株探フォールバック（最終手段） ---
KABUTAN_URL = "https://kabutan.jp/warning/record_w52_high_price/"


def perplexity_fetch_json(prompt: str, model: str) -> dict:
    url = "https://api.perplexity.ai/chat/completions"
    headers = {"Authorization": f"Bearer {PPX_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": model,  # "sonar-pro" or "sonar"
        "messages": [{"role": "user", "content": prompt}],
        "return_citations": True,
        "temperature": 0.0,
    }
    r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
    r.raise_for_status()
    content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    # JSONブロックを安全に抽出
    try:
        # contentがJSONそのもの or 前後に不要文字があるケース両対応
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1:
            js = content[start : end + 1]
            return json.loads(js)
    except Exception:
        pass
    return {}


def try_perplexity_codes() -> List[str]:
    if not PPX_KEY:
        return []
    # モデル切替＋プロンプト再試行（堅牢化）
    for model in ["sonar-pro", "sonar"]:
        for pr in PROMPTS:
            try:
                js = perplexity_fetch_json(pr, model)
                codes = js.get("codes") if isinstance(js, dict) else None
                if isinstance(codes, list):
                    # 4桁のみ
                    codes = [c for c in codes if re.fullmatch(r"\d{4}", str(c))]
                    if codes:
                        return sorted(set(codes))
            except Exception as e:
                print(f"[fetch][ppx] {model} failed: {e}", file=sys.stderr)
    return []


def kabutan_fallback_codes() -> List[str]:
    """最終フォールバック：株探の当日52週高値ページを1回取得して4桁コード抽出"""
    try:
        import bs4
        from bs4 import BeautifulSoup
    except Exception:
        print(
            "[fetch] beautifulsoup4/lxml が無いため株探フォールバック不可。",
            file=sys.stderr,
        )
        return []

    try:
        rr = requests.get(KABUTAN_URL, timeout=60)
        rr.raise_for_status()
        soup = BeautifulSoup(rr.text, "lxml")
        codes = []
        for tr in soup.select("table.stock_table tbody tr"):
            tds = tr.find_all("td")
            if not tds:
                continue
            code = tds[0].get_text(strip=True)
            if re.fullmatch(r"\d{4}", code):
                codes.append(code)
        return sorted(set(codes))
    except Exception as e:
        print(f"[fetch][kabutan] 失敗: {e}", file=sys.stderr)
        return []


def load_cache():
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(d):
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


CACHE = load_cache()


def yahoo_stock_type(symbol_t: str) -> str:
    now_ts = dt.datetime.utcnow().timestamp()
    cached = CACHE.get(symbol_t)
    if cached and now_ts - cached.get("ts", 0) < 24 * 3600:
        return (cached.get("asset") or "").upper()

    url = f"https://finance.yahoo.co.jp/quote/{symbol_t}/performance"
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
        text = resp.text
        match = re.search(r'"priceBoard":\{([^}]*)\}', text)
        asset = ""
        if match:
            block = match.group(1)
            m2 = re.search(r'"stockType":"([^"\\]+)"', block)
            if m2:
                asset = m2.group(1).upper()
        CACHE[symbol_t] = {"asset": asset, "ts": now_ts}
        save_cache(CACHE)
        time.sleep(THROTTLE)
        return asset
    except Exception as exc:
        print(f"[fetch][yahoo] asset type lookup failed for {symbol_t}: {exc}", file=sys.stderr)
        return ""


def main():
    # 1) Perplexityで取得（JSON想定）
    codes = try_perplexity_codes()

    # 2) 取れなければ、株探フォールバック
    if not codes:
        print("[fetch] コード抽出に失敗。株探フォールバックへ。", file=sys.stderr)
        codes = kabutan_fallback_codes()

    if not codes:
        print(
            "[fetch] それでもコードゼロ。既存symbols.txtを維持します。", file=sys.stderr
        )
        return

    # 3) .T付与 + ETF/ETN/REIT等の除外（Yahoo!ファイナンスで判定）
    symbols = []
    # シンボル作成ループはそのまま。asset が ETF/ETN/REIT のときだけ除外。
    for c in codes:
        sym_t = f"{c}.T"
        asset = yahoo_stock_type(sym_t)
        if asset in {"ETF", "ETN", "REIT", "CLOSEDEND FUND"}:
            continue
        symbols.append(sym_t)
        if len(symbols) >= MAX_SYMBOLS:
            break

    # 4) 全除外ならフォールバックでそのまま書く
    if not symbols:
        symbols = [f"{c}.T" for c in codes[:MAX_SYMBOLS]]

    with open(SYMBOLS_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(symbols) + "\n")
    print(f"[fetch] {len(symbols)} symbols written to {SYMBOLS_PATH}")


if __name__ == "__main__":
    main()
