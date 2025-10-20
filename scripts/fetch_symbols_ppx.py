import os, re, json, sys, time, datetime as dt
import requests
from typing import List

# --- 環境変数 ---
PPX_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
AV_KEY = os.environ.get("ALPHAVANTAGE_KEY", "")
THROTTLE = int(os.environ.get("THROTTLE_SECONDS", "13"))
MAX_SYMBOLS = int(os.environ.get("MAX_SYMBOLS", "200"))
USE_AV_OVERVIEW_FILTER = (
    os.environ.get("USE_AV_OVERVIEW_FILTER", "false").lower() == "true"
)
AV_OVERVIEW_DAILY_BUDGET = int(os.environ.get("AV_OVERVIEW_DAILY_BUDGET", "5"))

# --- パス ---
os.makedirs("config", exist_ok=True)
os.makedirs("cache", exist_ok=True)
SYMBOLS_PATH = "config/symbols.txt"
CACHE_PATH = "cache/overview.json"

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

# av_overview_asset_type をラップして日次回数を制御
_av_calls = 0


def _symbol_variants(symbol: str):
    """Alpha Vantage向けのシンボル候補を列挙（東京市場: .T/.TYO/.TSE/.JP, 無し）。"""
    seen = set()

    def push(value: str):
        v = value.strip()
        if v and v not in seen:
            seen.add(v)
            return True
        return False

    if push(symbol):
        yield symbol

    if "." in symbol:
        base, suffix = symbol.split(".", 1)
        if push(base):
            yield base

        suffix = suffix.upper()
        if suffix == "T":
            for alt in ("TYO", "TSE", "JP"):
                candidate = f"{base}.{alt}"
                if push(candidate):
                    yield candidate


def av_overview_asset_type(symbol_t: str) -> str:
    global _av_calls
    if not AV_KEY or not USE_AV_OVERVIEW_FILTER:
        return ""  # ← フィルタ無効なら何もせず戻る

    # まずキャッシュ
    now_ts = dt.datetime.utcnow().timestamp()
    if symbol_t in CACHE and now_ts - CACHE[symbol_t].get("ts", 0) < 7 * 24 * 3600:
        return (CACHE[symbol_t].get("asset") or "").upper()

    # 日次の呼び出し上限
    if _av_calls >= AV_OVERVIEW_DAILY_BUDGET:
        return ""  # ← これ以上AVは叩かない（残りはそのまま通す）

    url = "https://www.alphavantage.co/query"
    last_asset = ""

    for candidate in _symbol_variants(symbol_t):
        if _av_calls >= AV_OVERVIEW_DAILY_BUDGET:
            break

        _av_calls += 1
        try:
            params = {"function": "OVERVIEW", "symbol": candidate, "apikey": AV_KEY}
            rr = requests.get(url, params=params, timeout=60)
            rr.raise_for_status()
            j = rr.json()

            if isinstance(j, dict) and "Information" in j:
                break  # レート制限通知

            if isinstance(j, dict):
                asset = (j.get("AssetType") or "").upper()
                if asset:
                    CACHE[symbol_t] = {
                        "asset": asset,
                        "ts": now_ts,
                        "source": candidate,
                    }
                    save_cache(CACHE)
                    return asset
                last_asset = asset
        except Exception:
            pass
        finally:
            time.sleep(THROTTLE)

    if symbol_t not in CACHE:
        CACHE[symbol_t] = {"asset": last_asset, "ts": now_ts}
        save_cache(CACHE)
    return last_asset


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

    # 3) .T付与 + ETF/ETN/REIT等の除外（可能な範囲）
    symbols = []
    # シンボル作成ループはそのまま。asset が ETF/ETN/REIT のときだけ除外。
    for c in codes:
        sym_t = f"{c}.T"
        asset = av_overview_asset_type(sym_t)  # ← 上の制御が効く
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
