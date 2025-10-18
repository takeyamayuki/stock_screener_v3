import os, time, json
import requests, pandas as pd
from dateutil import tz
from datetime import datetime

API = "https://www.alphavantage.co/query"
KEY = os.environ["ALPHAVANTAGE_KEY"]
PPX_KEY = os.environ.get("PERPLEXITY_API_KEY")
THROTTLE = int(os.environ.get("THROTTLE_SECONDS", "13"))
MAX_SYMBOLS = int(os.environ.get("MAX_SYMBOLS", "60"))

JST = tz.gettz("Asia/Tokyo")
TODAY = datetime.now(JST).strftime("%Y%m%d")

SYMBOLS_PATH = "config/symbols.txt"
REPORT_CSV = f"reports/screen_{TODAY}.csv"
REPORT_MD = f"reports/screen_{TODAY}.md"
os.makedirs("reports", exist_ok=True)


def _get(params):
    r = requests.get(API, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def fetch_income_statement(symbol):
    data = _get({"function": "INCOME_STATEMENT", "symbol": symbol, "apikey": KEY})
    if "annualReports" not in data or "quarterlyReports" not in data:
        raise RuntimeError(f"INCOME_STATEMENT missing for {symbol}: {data}")
    return data["annualReports"], data["quarterlyReports"]


def to_int(v):
    try:
        return int(v)
    except:
        return None


def annual_checks(annual):
    rows = []
    for a in annual:
        rows.append(
            {
                "year": a.get("fiscalDateEnding"),
                "pretax": to_int(a.get("incomeBeforeTax")),  # 経常の近似：pretax
                "revenue": to_int(a.get("totalRevenue")),
            }
        )
    df = pd.DataFrame(rows).dropna().head(6)  # 最新→過去
    if len(df) < 3:
        return {"enough_years": False}
    df["pretax_yoy"] = df["pretax"].pct_change(periods=-1)
    df["margin"] = df["pretax"] / df["revenue"]
    window = df.head(5)  # 直近5年
    yoy = window["pretax_yoy"].dropna()
    stable_5_10 = all(0.05 <= x <= 0.10 for x in yoy) if len(yoy) >= 3 else False
    no_big_drop = all(x is None or x > -0.20 for x in yoy)
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
    df = pd.DataFrame(rows).dropna().head(8)  # 最新8Q
    if len(df) < 5:
        return {"enough_quarters": False}
    # YoYは4期前比較
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
    with open(SYMBOLS_PATH, "r", encoding="utf-8") as f:
        symbols = [x.strip() for x in f if x.strip()]
    symbols = symbols[:MAX_SYMBOLS]

    rows = []
    for i, sym in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] {sym}")
        try:
            annual, quarterly = fetch_income_statement(sym)
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
        except Exception as e:
            rows.append(
                {
                    "symbol": sym,
                    "score_0to7": None,
                    "notes": f"データ取得エラー: {e}",
                    "digest": "",
                }
            )
        time.sleep(THROTTLE)

    df = pd.DataFrame(rows).sort_values(
        ["score_0to7", "symbol"], ascending=[False, True]
    )
    df.to_csv(REPORT_CSV, index=False, encoding="utf-8")

    # Markdown
    lines = [
        f"# 日次スクリーナー（{TODAY} JST）\n",
        "※ 経常利益の近似として **incomeBeforeTax (preTax)** を使用。\n",
        "|Symbol|Score|直近1Y YoY|直近2Y CAGR|Q(pretax YoY)|Q(rev YoY)|Q基準達成|連続性|加速|率改善|メモ|",
        "|---|---:|---:|---:|---:|---:|:---:|:---:|:---:|:---:|---|",
    ]
    for r in df.to_dict("records"):
        row = (
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
        lines.append(row)
        if r.get("digest"):
            lines.append(f"\n**{r['symbol']} 要約**\n\n{r['digest']}\n")

    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("Saved:", REPORT_CSV, REPORT_MD)


if __name__ == "__main__":
    main()
