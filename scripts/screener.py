import os, time, json, shutil
import requests, pandas as pd
from dateutil import tz
from datetime import datetime, timedelta

API = "https://www.alphavantage.co/query"
KEY = os.environ["ALPHAVANTAGE_KEY"]
PPX_KEY = os.environ.get("PERPLEXITY_API_KEY")
THROTTLE = int(os.environ.get("THROTTLE_SECONDS", "13"))
MAX_SYMBOLS = int(os.environ.get("MAX_SYMBOLS", "60"))
MAX_DAILY_CALLS = int(
    os.environ.get("ALPHAVANTAGE_MAX_DAILY_CALLS", "20")
)  # ★追加：日次上限
CACHE_DAYS = int(os.environ.get("ALPHAVANTAGE_CACHE_DAYS", "7"))

JST = tz.gettz("Asia/Tokyo")
TODAY = datetime.now(JST).strftime("%Y%m%d")

SYMBOLS_PATH = "config/symbols.txt"
REPORT_CSV = f"reports/screen_{TODAY}.csv"
REPORT_MD = f"reports/screen_{TODAY}.md"
os.makedirs("reports", exist_ok=True)

INCACHE_DIR = "cache/av_income"
os.makedirs(INCACHE_DIR, exist_ok=True)

# OVERVIEW フォールバック用キャッシュ
OVERCACHE_DIR = "cache/av_overview"
os.makedirs(OVERCACHE_DIR, exist_ok=True)


class RateLimitError(Exception):
    pass


def _get(params):
    r = requests.get(API, params=params, timeout=60)
    r.raise_for_status()
    j = r.json()
    # AlphaVantageのレート制限/日次上限メッセージに反応
    if isinstance(j, dict) and "Information" in j:
        raise RateLimitError(j.get("Information"))
    return j


def _cache_path(symbol: str) -> str:
    safe = symbol.replace("/", "_")
    return os.path.join(INCACHE_DIR, f"{safe}.json")


def _load_income_cache(symbol: str):
    p = _cache_path(symbol)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        ts = data.get("_cached_at")
        if not ts:
            return None
        cached_dt = datetime.fromisoformat(ts)
        if datetime.utcnow() - cached_dt > timedelta(days=CACHE_DAYS):
            return None
        return data
    except Exception:
        return None


def _save_income_cache(symbol: str, data: dict):
    data = dict(data)
    data["_cached_at"] = datetime.utcnow().isoformat()
    tmp = _cache_path(symbol) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    shutil.move(tmp, _cache_path(symbol))


def _ov_cache_path(symbol: str) -> str:
    safe = symbol.replace("/", "_")
    return os.path.join(OVERCACHE_DIR, f"{safe}.json")


def _load_overview_cache(symbol: str):
    p = _ov_cache_path(symbol)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        ts = data.get("_cached_at")
        if not ts:
            return None
        cached_dt = datetime.fromisoformat(ts)
        if datetime.utcnow() - cached_dt > timedelta(days=CACHE_DAYS):
            return None
        return data
    except Exception:
        return None


def _save_overview_cache(symbol: str, data: dict):
    data = dict(data)
    data["_cached_at"] = datetime.utcnow().isoformat()
    tmp = _ov_cache_path(symbol) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    shutil.move(tmp, _ov_cache_path(symbol))


def fetch_income_statement(symbol, call_budget):
    """
    call_budget: 残りAPIコール可能数（0ならAPIを叩かずキャッシュのみ）
    戻り値: (annualReports, quarterlyReports, used_api_call: bool)
    """
    # 1) キャッシュ優先
    cached = _load_income_cache(symbol)
    if cached and "annualReports" in cached and "quarterlyReports" in cached:
        return cached["annualReports"], cached["quarterlyReports"], False

    # 2) 予算がなければ失敗扱い（上位でスキップ）
    if call_budget <= 0:
        raise RateLimitError("Daily call budget exhausted (pre-check).")

    # 3) APIコール
    data = _get({"function": "INCOME_STATEMENT", "symbol": symbol, "apikey": KEY})
    if "annualReports" not in data or "quarterlyReports" not in data:
        # データ欠損は通常エラーとして扱う
        raise RuntimeError(f"INCOME_STATEMENT missing for {symbol}: {data}")
    _save_income_cache(symbol, data)
    time.sleep(THROTTLE)
    return data["annualReports"], data["quarterlyReports"], True


def fetch_overview(symbol, call_budget):
    """
    Alpha Vantage OVERVIEW フォールバック。
    戻り値: (overview_dict, used_api_call: bool)
    """
    cached = _load_overview_cache(symbol)
    if cached and isinstance(cached, dict) and cached:
        return cached, False

    if call_budget <= 0:
        raise RateLimitError("Daily call budget exhausted (pre-check).")

    data = _get({"function": "OVERVIEW", "symbol": symbol, "apikey": KEY})
    # OVERVIEWはキーが少なくても空dictで返ることがあるため、空dictでも行として処理可能にする
    if not isinstance(data, dict):
        raise RuntimeError(f"OVERVIEW missing for {symbol}: {data}")
    _save_overview_cache(symbol, data)
    time.sleep(THROTTLE)
    return data, True


def to_int(v):
    try:
        return int(v)
    except:
        return None


def to_float(v):
    try:
        return float(v)
    except:
        return None


def annual_checks(annual):
    rows = []
    for a in annual:
        rows.append(
            {
                "year": a.get("fiscalDateEnding"),
                "pretax": to_int(a.get("incomeBeforeTax")),  # 経常の近似: pretax
                "revenue": to_int(a.get("totalRevenue")),
            }
        )
    df = pd.DataFrame(rows).dropna().head(6)
    if len(df) < 3:
        return {"enough_years": False}
    df["pretax_yoy"] = df["pretax"].pct_change(periods=-1)
    df["margin"] = df["pretax"] / df["revenue"]
    window = df.head(5)
    yoy = window["pretax_yoy"].dropna()
    stable_5_10 = all(0.05 <= x <= 0.10 for x in yoy) if len(yoy) >= 3 else False
    no_big_drop = all((x is None) or (x > -0.20) for x in yoy)
    last1 = yoy.iloc[0] if len(yoy) >= 1 else None
    if (
        len(window) >= 3
        and window["pretax"].notna().iloc[0]
        and window["pretax"].notna().iloc[2]
    ):
        last2_cagr = (window["pretax"].iloc[0] / window["pretax"].iloc[2]) ** (
            1 / 2
        ) - 1
    else:
        last2_cagr = None
    return dict(
        enough_years=True,
        stable_5_10=stable_5_10,
        no_big_drop=no_big_drop,
        last1_yoy=last1,
        last2_cagr=last2_cagr,
        annual_df=df,
    )


def quarterly_checks(quarterly):
    rows = []
    for q in quarterly:
        rows.append(
            {
                "quarter": q.get("fiscalDateEnding"),
                "pretax": to_int(q.get("incomeBeforeTax")),
                "revenue": to_int(q.get("totalRevenue")),
            }
        )
    df = pd.DataFrame(rows).dropna().head(8)
    if len(df) < 5:
        return {"enough_quarters": False}
    df["pretax_yoy"] = (df["pretax"] - df["pretax"].shift(-4)) / df["pretax"].shift(-4)
    df["revenue_yoy"] = (df["revenue"] - df["revenue"].shift(-4)) / df["revenue"].shift(
        -4
    )
    df["margin"] = df["pretax"] / df["revenue"]
    last3 = df.iloc[0:3].copy()
    last2 = df.iloc[0:2].copy()
    lastQ_ok = (
        pd.notna(last3["pretax_yoy"].iloc[0]) and last3["pretax_yoy"].iloc[0] >= 0.20
    ) and (
        pd.notna(last3["revenue_yoy"].iloc[0]) and last3["revenue_yoy"].iloc[0] >= 0.10
    )
    sequential_ok = (
        (last2["pretax_yoy"] >= 0.20).all() and (last2["revenue_yoy"] >= 0.10).all()
    ) or (
        (last3["pretax_yoy"] >= 0.20).sum() >= 2
        and (last3["revenue_yoy"] >= 0.10).sum() >= 2
    )
    accelerating = (
        pd.notna(df["pretax_yoy"].iloc[0])
        and pd.notna(df["pretax_yoy"].iloc[1])
        and df["pretax_yoy"].iloc[0] >= df["pretax_yoy"].iloc[1]
    )
    improving_margin = (
        pd.notna(df["margin"].iloc[0])
        and pd.notna(df["margin"].iloc[4])
        and df["margin"].iloc[0] >= df["margin"].iloc[4]
    )
    return dict(
        enough_quarters=True,
        lastQ_ok=bool(lastQ_ok),
        sequential_ok=bool(sequential_ok),
        accelerating=bool(accelerating),
        improving_margin=bool(improving_margin),
        quarterly_df=df,
    )


def overview_quarterly_checks(overview: dict):
    """
    OVERVIEWの乏しい指標から四半期相当の最低限チェックを近似。
    期待する主なキー: QuarterlyEarningsGrowthYOY, QuarterlyRevenueGrowthYOY, ProfitMargin
    見つからなければNone扱い。
    """
    eg = to_float(overview.get("QuarterlyEarningsGrowthYOY"))
    rg = to_float(overview.get("QuarterlyRevenueGrowthYOY"))
    pm = to_float(overview.get("ProfitMargin"))

    lastQ_ok = (eg is not None and eg >= 0.20) and (rg is not None and rg >= 0.10)
    # 連続性/加速は情報がないため、単発のしきい値のみで判断
    sequential_ok = bool(lastQ_ok)
    accelerating = False  # 不明
    improving_margin = (pm is not None and pm >= 0)  # マージンがマイナスでなければ一応OKとみなす

    return dict(
        enough_quarters=True,
        lastQ_ok=bool(lastQ_ok),
        sequential_ok=bool(sequential_ok),
        accelerating=bool(accelerating),
        improving_margin=bool(improving_margin),
        quarterly_df=None,
    )


def score(ann, qrt):
    s, notes = 0, []
    if ann.get("enough_years"):
        if ann.get("stable_5_10"):
            s += 1
        else:
            notes.append("年率5–10%の安定成長は未達")
        if ann.get("no_big_drop"):
            s += 1
        else:
            notes.append("途中に大幅減益あり")
        if ann.get("last1_yoy") is not None and ann["last1_yoy"] >= 0.20:
            s += 1
        else:
            notes.append("直近1年+20%未満")
        if ann.get("last2_cagr") is not None and ann["last2_cagr"] >= 0.20:
            s += 1
        else:
            notes.append("直近2年CAGR+20%未満")
    else:
        notes.append("年次データ不足")
    if qrt.get("enough_quarters"):
        if qrt.get("lastQ_ok"):
            s += 1
        else:
            notes.append("直近Q: pretax+20% & 売上+10% 未達")
        if qrt.get("sequential_ok"):
            s += 1
        else:
            notes.append("直近2–3Qの連続クリア未達")
        if qrt.get("accelerating"):
            s += 1
        else:
            notes.append("pretax成長の加速なし")
        if qrt.get("improving_margin"):
            s += 1
        else:
            notes.append("売上高経常(pretax)利益率のYoY改善なし")
    else:
        notes.append("四半期データ不足")
    return s, "; ".join(notes)


def perplexity_digest(symbol: str):
    if not PPX_KEY:
        return ""
    url = "https://api.perplexity.ai/chat/completions"
    headers = {"Authorization": f"Bearer {PPX_KEY}", "Content-Type": "application/json"}
    prompt = f"日本株 {symbol} の直近決算/見通しを日本語で3点に要約し、各点に角括弧で出典URLを必ず付けてください。"
    payload = {
        "model": "sonar-pro",
        "messages": [{"role": "user", "content": prompt}],
        "return_citations": True,
    }
    try:
        r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
        r.raise_for_status()
        j = r.json()
        return j.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        return f"(Perplexity要約失敗: {e})"


def perc(x):
    return "" if x is None else f"{x*100:.1f}%"


def main():
    # symbols 読み込みと防御
    if not os.path.exists(SYMBOLS_PATH):
        print(f"[screen] {SYMBOLS_PATH} がありません。終了。")
        pd.DataFrame([]).to_csv(REPORT_CSV, index=False, encoding="utf-8")
        with open(REPORT_MD, "w", encoding="utf-8") as f:
            f.write(
                f"# 日次スクリーナー（{TODAY} JST）\n\nシンボルファイルが見つかりませんでした。"
            )
        print("Saved (empty):", REPORT_CSV, REPORT_MD)
        return

    with open(SYMBOLS_PATH, "r", encoding="utf-8") as f:
        symbols = [x.strip() for x in f if x.strip() and not x.strip().startswith("#")]
    symbols = symbols[:MAX_SYMBOLS]
    if not symbols:
        print("[screen] シンボルが0件のため、処理せず終了（正常）。")
        pd.DataFrame([]).to_csv(REPORT_CSV, index=False, encoding="utf-8")
        with open(REPORT_MD, "w", encoding="utf-8") as f:
            f.write(f"# 日次スクリーナー（{TODAY} JST）\n\nシンボルが0件でした。")
        print("Saved (empty):", REPORT_CSV, REPORT_MD)
        return

    rows = []
    errors = []  # 表に出さない。注記にまとめる
    skipped = []  # 日次上限等で未処理になった銘柄
    used_api_calls = 0
    used_cache = 0
    hit_rate_limit = False

    for i, sym in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] {sym}")
        try:
            budget_left = MAX_DAILY_CALLS - used_api_calls
            # 事前にキャッシュ有無を確認し、APIコールが発生した場合の失敗も計上できるようにする
            income_cached = _load_income_cache(sym)
            expect_api_call = income_cached is None and budget_left > 0

            annual, quarterly, used_api = fetch_income_statement(sym, budget_left)
            # 成否に関わらず、呼び出しが発生した場合は使用回数に反映
            used_api_calls += int(used_api)
            used_cache += int(not used_api)

            ann = annual_checks(annual)
            qrt = quarterly_checks(quarterly)
            sc, notes = score(ann, qrt)

            last1 = ann.get("last1_yoy")
            last2 = ann.get("last2_cagr")
            lastQ = (
                qrt.get("quarterly_df").iloc[0] if qrt.get("enough_quarters") else None
            )
            lastQ_pre_yoy = (
                None
                if (lastQ is None or pd.isna(lastQ["pretax_yoy"]))
                else float(lastQ["pretax_yoy"])
            )
            lastQ_rev_yoy = (
                None
                if (lastQ is None or pd.isna(lastQ["revenue_yoy"]))
                else float(lastQ["revenue_yoy"])
            )

            rows.append(
                {
                    "symbol": sym,
                    "score_0to7": sc,
                    "annual_last1_yoy": None if last1 is None else round(last1, 4),
                    "annual_last2_cagr": None if last2 is None else round(last2, 4),
                    "q_last_pretax_yoy": (
                        None if lastQ_pre_yoy is None else round(lastQ_pre_yoy, 4)
                    ),
                    "q_last_revenue_yoy": (
                        None if lastQ_rev_yoy is None else round(lastQ_rev_yoy, 4)
                    ),
                    "q_last_ok_20_10": qrt.get("lastQ_ok"),
                    "q_seq_ok": qrt.get("sequential_ok"),
                    "q_accelerating": qrt.get("accelerating"),
                    "q_improving_margin": qrt.get("improving_margin"),
                    "notes": notes,
                    "digest": perplexity_digest(sym) if sc >= 3 else "",
                }
            )

        except RateLimitError as e:
            hit_rate_limit = True
            errors.append(f"{sym}: {str(e)}")
            # 残り銘柄はスキップ
            skipped.extend(symbols[i:])  # 現在の次から最後まで
            break

        except Exception as e:
            # INCOME_STATEMENT のAPI呼び出しが発生していた場合は失敗でも1回分加算
            try:
                used_api_calls += int(expect_api_call)
            except Exception:
                pass
            # INCOME_STATEMENTが欠損など → OVERVIEWでフォールバックを試す
            try:
                budget_left = MAX_DAILY_CALLS - used_api_calls
                # OVERVIEWのキャッシュ状況を確認し、失敗時でも適切にカウントする
                overview_cached = _load_overview_cache(sym)
                expect_api_call_ov = overview_cached is None and budget_left > 0

                overview, used_api_ov = fetch_overview(sym, budget_left)
                used_api_calls += int(used_api_ov)
                used_cache += int(not used_api_ov)

                ann = {"enough_years": False}  # 年次は不明
                qrt = overview_quarterly_checks(overview)
                sc, notes = score(ann, qrt)
                notes = ("(OVERVIEW fallback) " + notes).strip()

                # 主要表示値（年次はNone、四半期はOVERVIEWのYoY）
                lastQ_pre_yoy = to_float(overview.get("QuarterlyEarningsGrowthYOY"))
                lastQ_rev_yoy = to_float(overview.get("QuarterlyRevenueGrowthYOY"))

                rows.append(
                    {
                        "symbol": sym,
                        "score_0to7": sc,
                        "annual_last1_yoy": None,
                        "annual_last2_cagr": None,
                        "q_last_pretax_yoy": lastQ_pre_yoy,
                        "q_last_revenue_yoy": lastQ_rev_yoy,
                        "q_last_ok_20_10": qrt.get("lastQ_ok"),
                        "q_seq_ok": qrt.get("sequential_ok"),
                        "q_accelerating": qrt.get("accelerating"),
                        "q_improving_margin": qrt.get("improving_margin"),
                        "notes": notes,
                        "digest": perplexity_digest(sym) if sc >= 3 else "",
                    }
                )
            except RateLimitError as e2:
                hit_rate_limit = True
                errors.append(f"{sym}: {str(e2)}")
                skipped.extend(symbols[i:])
                break
            except Exception as e2:
                # OVERVIEW のAPI呼び出しが発生していた場合は失敗でも1回分加算
                try:
                    used_api_calls += int(expect_api_call_ov)
                except Exception:
                    pass
                # どちらも取得できない場合のみエラー記録
                errors.append(f"{sym}: {e}; fallback: {e2}")

    # もし残り予算ゼロで未処理が出た場合、それもスキップとして記録
    if used_api_calls >= MAX_DAILY_CALLS:
        # キャッシュ命中なら処理続行しているはずだが、未処理が残る可能性がある
        # ループのbreakはしないが、明示的に記録
        pass

    # DataFrame化（表は成功銘柄のみ）
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["score_0to7", "symbol"], ascending=[False, True])
        df.to_csv(REPORT_CSV, index=False, encoding="utf-8")
    else:
        # 空でもCSVを出す
        df.to_csv(REPORT_CSV, index=False, encoding="utf-8")

    # Markdown: ヘッダ＋集計＋表＋注記
    summary_lines = [
        f"# 日次スクリーナー（{TODAY} JST）\n",
        "※ 経常利益の近似として **incomeBeforeTax (preTax)** を使用。\n",
        f"- 処理銘柄（表に掲載）: **{len(df)}** 件\n",
        f"- Alpha Vantage API 使用回数: **{used_api_calls}** / 上限 {MAX_DAILY_CALLS}\n",
        f"- キャッシュ命中: **{used_cache}** 件\n",
    ]
    if hit_rate_limit:
        summary_lines.append(f"- ⚠️ レート制限に到達。以降の銘柄はスキップしました。\n")
    if skipped:
        summary_lines.append(
            f"- スキップした銘柄（上限/制限等）: {', '.join(skipped)}\n"
        )

    table_lines = []
    if not df.empty:
        table_lines += [
            "|Symbol|Score|直近1Y YoY|直近2Y CAGR|Q(pretax YoY)|Q(rev YoY)|Q基準達成|連続性|加速|率改善|メモ|",
            "|---|---:|---:|---:|---:|---:|:---:|:---:|:---:|:---:|---|",
        ]
        for r in df.to_dict("records"):
            table_lines.append(
                f"|{r['symbol']}|{r.get('score_0to7','')}|"
                f"{perc(r.get('annual_last1_yoy'))}|"
                f"{perc(r.get('annual_last2_cagr'))}|"
                f"{perc(r.get('q_last_pretax_yoy'))}|"
                f"{perc(r.get('q_last_revenue_yoy'))}|"
                f"{'✅' if r.get('q_last_ok_20_10') else '—'}|"
                f"{'✅' if r.get('q_seq_ok') else '—'}|"
                f"{'✅' if r.get('q_accelerating') else '—'}|"
                f"{'✅' if r.get('q_improving_margin') else '—'}|"
                f"{r.get('notes','')}|"
            )
            if r.get("digest"):
                table_lines.append(f"\n**{r['symbol']} 要約**\n\n{r['digest']}\n")
    else:
        table_lines.append("> 表示可能なデータがありませんでした。")

    notes_lines = []
    if errors:
        notes_lines += ["\n### 注記（処理できなかった銘柄など）\n"]
        for e in errors[:50]:
            notes_lines.append(f"- {e}")
        if len(errors) > 50:
            notes_lines.append(f"- …ほか {len(errors)-50} 件")

    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(summary_lines + ["\n"] + table_lines + ["\n"] + notes_lines))

    print("Saved:", REPORT_CSV, REPORT_MD)


if __name__ == "__main__":
    main()
