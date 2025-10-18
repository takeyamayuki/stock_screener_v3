import os, re, json, sys, time, datetime as dt
import requests

PPX_KEY = os.environ["PERPLEXITY_API_KEY"]
AV_KEY = os.environ.get("ALPHAVANTAGE_KEY", "")
THROTTLE = int(os.environ.get("THROTTLE_SECONDS", "13"))
MAX_SYMBOLS = int(os.environ.get("MAX_SYMBOLS", "200"))

os.makedirs("config", exist_ok=True)
os.makedirs("cache", exist_ok=True)
SYMBOLS_PATH = "config/symbols.txt"
CACHE_PATH = "cache/overview.json"

PROMPT = (
    "今日（日本時間）の日本株で、52週高値を更新した銘柄を、"
    "東証プライム・スタンダード・グロース市場の上場企業に限定して列挙してください。"
    "ETF・ETN・REIT・投資信託・投資法人は除外してください。"
    "出力は1行1銘柄で「銘柄名 証券コード（4桁）」の形式。"
    "最後に参考にした最新情報のURLを列挙してください。"
)


def perplexity_fetch_text(prompt: str) -> str:
    url = "https://api.perplexity.ai/chat/completions"
    headers = {"Authorization": f"Bearer {PPX_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "sonar-pro",
        "messages": [{"role": "user", "content": prompt}],
        "return_citations": True,
    }
    r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
    r.raise_for_status()
    j = r.json()
    return j.get("choices", [{}])[0].get("message", {}).get("content", "")


def extract_codes(text: str):
    # 4桁コード抽出（重複排除）
    codes = sorted(set(re.findall(r"\b(\d{4})\b", text)))
    return codes


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


def av_overview_asset_type(symbol_t: str) -> str:
    """Alpha Vantage OVERVIEWでAssetTypeを取得。7日キャッシュ。"""
    if not AV_KEY:
        return ""
    now_ts = dt.datetime.utcnow().timestamp()
    if symbol_t in CACHE:
        rec = CACHE[symbol_t]
        if now_ts - rec.get("ts", 0) < 7 * 24 * 3600:
            return rec.get("asset", "")
    try:
        url = "https://www.alphavantage.co/query"
        params = {"function": "OVERVIEW", "symbol": symbol_t, "apikey": AV_KEY}
        rr = requests.get(url, params=params, timeout=60)
        rr.raise_for_status()
        j = rr.json()
        asset = (j.get("AssetType") or "").upper()
        CACHE[symbol_t] = {"asset": asset, "ts": now_ts}
        save_cache(CACHE)
        return asset
    except Exception:
        return ""
    finally:
        time.sleep(THROTTLE)


def main():
    # 1) 52週高値の銘柄（4桁コード）をPerplexityで収集
    try:
        text = perplexity_fetch_text(PROMPT)
    except Exception as e:
        print(f"[fetch] Perplexity API失敗: {e}", file=sys.stderr)
        if os.path.exists(SYMBOLS_PATH):
            print("[fetch] 既存symbols.txtを維持します。")
            return
        else:
            raise

    codes = extract_codes(text)
    if not codes:
        print("[fetch] コードが抽出できませんでした。既存symbols.txtを維持します。")
        return

    # 2) .T付与 + ETF/ETN/REIT等の除外（できる範囲）
    symbols = []
    for c in codes:
        sym_t = f"{c}.T"
        asset = av_overview_asset_type(sym_t) if AV_KEY else ""
        if asset in {"ETF", "ETN", "REIT", "CLOSEDEND FUND"}:
            continue
        symbols.append(sym_t)
        if len(symbols) >= MAX_SYMBOLS:
            break

    # 3) 全除外だった場合のフォールバック
    if not symbols:
        symbols = [f"{c}.T" for c in codes[:MAX_SYMBOLS]]

    with open(SYMBOLS_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(symbols) + "\n")
    print(f"[fetch] {len(symbols)} symbols written to {SYMBOLS_PATH}")


if __name__ == "__main__":
    main()
