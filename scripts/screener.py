from __future__ import annotations

import os
from datetime import datetime
from typing import List, Tuple

import pandas as pd
import requests
from dateutil import tz

from providers import FinancialDataProvider

PPX_KEY = os.environ.get("PERPLEXITY_API_KEY")
THROTTLE = int(os.environ.get("THROTTLE_SECONDS", "13"))
MAX_SYMBOLS = int(os.environ.get("MAX_SYMBOLS", "60"))

JST = tz.gettz("Asia/Tokyo")
TODAY = datetime.now(JST).strftime("%Y%m%d")

SYMBOLS_PATH = "config/symbols.txt"
REPORT_CSV = f"reports/screen_{TODAY}.csv"
REPORT_MD = f"reports/screen_{TODAY}.md"
os.makedirs("reports", exist_ok=True)


def to_dataframe(records, value_key: str, revenue_key: str) -> pd.DataFrame:
    rows = []
    for record in records:
        rows.append(
            {
                "period": record.period_label,
                "end_date": record.end_date,
                "revenue": record.revenue,
                value_key: record.ordinary_income,
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.dropna(subset=[value_key, "revenue"])
        df = df.sort_values("end_date", ascending=False).reset_index(drop=True)
    return df


def annual_checks(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"enough_years": False}
    df = df.copy()
    df["ordinary_yoy"] = df["ordinary_income"].pct_change(periods=-1)
    df["margin"] = df["ordinary_income"] / df["revenue"]
    window = df.head(5)
    yoy_series = window["ordinary_yoy"].dropna()
    stable_5_10 = all(0.05 <= x <= 0.10 for x in yoy_series) if len(yoy_series) >= 3 else False
    no_big_drop = all(x > -0.20 for x in yoy_series) if not yoy_series.empty else False
    last1 = yoy_series.iloc[0] if len(yoy_series) >= 1 else None
    if len(window) >= 3 and pd.notna(window["ordinary_income"].iloc[0]) and pd.notna(window["ordinary_income"].iloc[2]):
        last2_cagr = (
            (window["ordinary_income"].iloc[0] / window["ordinary_income"].iloc[2]) ** (1 / 2)
            - 1
        )
    else:
        last2_cagr = None
    return {
        "enough_years": len(df) >= 3,
        "stable_5_10": stable_5_10,
        "no_big_drop": no_big_drop,
        "last1_yoy": last1,
        "last2_cagr": last2_cagr,
        "annual_df": df,
    }


def quarterly_checks(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"enough_quarters": False}
    df = df.copy()
    df["ordinary_yoy"] = (df["ordinary_income"] - df["ordinary_income"].shift(-4)) / df["ordinary_income"].shift(-4)
    df["revenue_yoy"] = (df["revenue"] - df["revenue"].shift(-4)) / df["revenue"].shift(-4)
    df["margin"] = df["ordinary_income"] / df["revenue"]
    last3 = df.iloc[0:3].copy()
    last2 = df.iloc[0:2].copy()
    last_q_ok = (
        pd.notna(last3["ordinary_yoy"].iloc[0])
        and last3["ordinary_yoy"].iloc[0] >= 0.20
        and pd.notna(last3["revenue_yoy"].iloc[0])
        and last3["revenue_yoy"].iloc[0] >= 0.10
    )
    sequential_ok = (
        (last2["ordinary_yoy"] >= 0.20).all() and (last2["revenue_yoy"] >= 0.10).all()
    ) or (
        (last3["ordinary_yoy"] >= 0.20).sum() >= 2 and (last3["revenue_yoy"] >= 0.10).sum() >= 2
    )
    accelerating = (
        pd.notna(df["ordinary_yoy"].iloc[0])
        and pd.notna(df["ordinary_yoy"].iloc[1])
        and df["ordinary_yoy"].iloc[0] >= df["ordinary_yoy"].iloc[1]
    )
    improving_margin = (
        pd.notna(df["margin"].iloc[0])
        and pd.notna(df["margin"].iloc[4])
        and df["margin"].iloc[0] >= df["margin"].iloc[4]
    ) if len(df) >= 5 else False
    return {
        "enough_quarters": len(df) >= 5,
        "lastQ_ok": bool(last_q_ok),
        "sequential_ok": bool(sequential_ok),
        "accelerating": bool(accelerating),
        "improving_margin": bool(improving_margin),
        "quarterly_df": df,
    }


def score(annual_result: dict, quarterly_result: dict) -> Tuple[int, str]:
    s, notes = 0, []
    if annual_result.get("enough_years"):
        if annual_result.get("stable_5_10"):
            s += 1
        else:
            notes.append("年率5–10%の安定成長は未達")
        if annual_result.get("no_big_drop"):
            s += 1
        else:
            notes.append("途中に大幅減益あり")
        if annual_result.get("last1_yoy") is not None and annual_result["last1_yoy"] >= 0.20:
            s += 1
        else:
            notes.append("直近1年+20%未満")
        if annual_result.get("last2_cagr") is not None and annual_result["last2_cagr"] >= 0.20:
            s += 1
        else:
            notes.append("直近2年CAGR+20%未満")
    else:
        notes.append("年次データ不足")

    if quarterly_result.get("enough_quarters"):
        if quarterly_result.get("lastQ_ok"):
            s += 1
        else:
            notes.append("直近Q: 経常+20% & 売上+10% 未達")
        if quarterly_result.get("sequential_ok"):
            s += 1
        else:
            notes.append("直近2–3Qの連続クリア未達")
        if quarterly_result.get("accelerating"):
            s += 1
        else:
            notes.append("経常成長の加速なし")
        if quarterly_result.get("improving_margin"):
            s += 1
        else:
            notes.append("経常利益率のYoY改善なし")
    else:
        notes.append("四半期データ不足")

    return s, "; ".join(notes)


def perplexity_digest(symbol: str) -> str:
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
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as exc:
        return f"(Perplexity要約失敗: {exc})"


def load_symbols(path: str) -> List[str]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        symbols = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    return symbols


def perc(value: float) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{value * 100:.1f}%"


def main():
    symbols = load_symbols(SYMBOLS_PATH)[:MAX_SYMBOLS]
    if not symbols:
        print(f"[screen] シンボルが0件のため、処理せず終了（正常）。")
        pd.DataFrame([]).to_csv(REPORT_CSV, index=False, encoding="utf-8")
        with open(REPORT_MD, "w", encoding="utf-8") as f:
            f.write(f"# 日次スクリーナー（{TODAY} JST）\n\nシンボルが0件でした。")
        return

    provider = FinancialDataProvider()
    rows = []
    errors: List[str] = []

    for idx, symbol in enumerate(symbols, 1):
        print(f"[{idx}/{len(symbols)}] {symbol}")
        try:
            annual_records = provider.get_annual(symbol)
            quarterly_records = provider.get_quarterly(symbol)

            annual_df = to_dataframe(annual_records, "ordinary_income", "revenue")
            quarterly_df = to_dataframe(quarterly_records, "ordinary_income", "revenue")

            annual_result = annual_checks(annual_df)
            quarterly_result = quarterly_checks(quarterly_df)

            sc, notes = score(annual_result, quarterly_result)

            last1 = annual_result.get("last1_yoy")
            last2 = annual_result.get("last2_cagr")
            lastQ = (
                quarterly_result.get("quarterly_df").iloc[0]
                if quarterly_result.get("enough_quarters") and quarterly_result.get("quarterly_df") is not None
                else None
            )
            lastQ_pre_yoy = None if lastQ is None else lastQ.get("ordinary_yoy")
            lastQ_rev_yoy = None if lastQ is None else lastQ.get("revenue_yoy")

            info = provider.get_company_info(symbol)
            rows.append(
                {
                    "symbol": symbol,
                    "name_jp": info.name if info else "",
                    "market": info.market if info else "",
                    "score_0to7": sc,
                    "annual_last1_yoy": last1,
                    "annual_last2_cagr": last2,
                    "q_last_pretax_yoy": lastQ_pre_yoy,
                    "q_last_revenue_yoy": lastQ_rev_yoy,
                    "q_last_ok_20_10": quarterly_result.get("lastQ_ok"),
                    "q_seq_ok": quarterly_result.get("sequential_ok"),
                    "q_accelerating": quarterly_result.get("accelerating"),
                    "q_improving_margin": quarterly_result.get("improving_margin"),
                    "notes": notes,
                    "digest": perplexity_digest(symbol) if sc >= 3 else "",
                }
            )
        except Exception as exc:
            errors.append(f"{symbol}: {exc}")

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["score_0to7", "symbol"], ascending=[False, True])
    df.to_csv(REPORT_CSV, index=False, encoding="utf-8")

    summary_lines = [
        f"# 日次スクリーナー（{TODAY} JST）\n",
        "※ データ出典: Yahoo!ファイナンス / 株探（かぶたん）。\n",
        f"- 処理銘柄（表に掲載）: **{len(df)}** 件\n",
        f"- 入力シンボル数: {len(symbols)} 件\n",
    ]

    column_guides = [
        "- `Symbol`: 東証ティッカー（例: 2726.T）。",
        "- `銘柄名`: Kabutanより取得した日本語正式名。",
        "- `市場`: 東証の市場区分（プライム/スタンダード/グロースなど）。",
        "- `Score`: 年次・四半期チェックの合計スコア（0〜7）。",
        "- `直近1Y YoY`: 直近通期の経常利益YoY（前年比）。",
        "- `直近2Y CAGR`: 直近2期の経常利益CAGR。",
        "- `Q(pretax YoY)`: 直近四半期の経常利益YoY。",
        "- `Q(rev YoY)`: 直近四半期の売上高YoY。",
        "- `Q基準達成`: 直近四半期で「経常+20% & 売上+10%」を満たしたか。",
        "- `連続性`: 直近2-3四半期で基準を複数回満たしたか。",
        "- `加速`: 経常YoYが直近で加速しているか。",
        "- `率改善`: 経常利益率が前年同期比で改善しているか。",
        "- `メモ`: 未達項目や注意点のまとめ。",
    ]

    table_lines: List[str]
    digest_lines: List[str] = []
    if not df.empty:
        table_lines = [
            "|Symbol|銘柄名|市場|Score|直近1Y YoY|直近2Y CAGR|Q(pretax YoY)|Q(rev YoY)|Q基準達成|連続性|加速|率改善|メモ|",
            "|---|---|---|---:|---:|---:|---:|---:|:---:|:---:|:---:|:---:|---|",
        ]
        for record in df.to_dict("records"):
            table_lines.append(
                f"|{record['symbol']}|{record.get('name_jp', '')}|{record.get('market', '')}|"
                f"{record.get('score_0to7', '')}|"
                f"{perc(record.get('annual_last1_yoy'))}|"
                f"{perc(record.get('annual_last2_cagr'))}|"
                f"{perc(record.get('q_last_pretax_yoy'))}|"
                f"{perc(record.get('q_last_revenue_yoy'))}|"
                f"{'✅' if record.get('q_last_ok_20_10') else '—'}|"
                f"{'✅' if record.get('q_seq_ok') else '—'}|"
                f"{'✅' if record.get('q_accelerating') else '—'}|"
                f"{'✅' if record.get('q_improving_margin') else '—'}|"
                f"{record.get('notes', '')}|"
            )
            if record.get("digest"):
                digest_lines.append(
                    f"**{record['symbol']} 要約**\n\n{record['digest']}\n"
                )
    else:
        table_lines = ["> 表示可能なデータがありませんでした。"]

    notes_lines: List[str] = []
    if errors:
        notes_lines.append("\n### 注記（処理できなかった銘柄など）\n")
        for err in errors[:50]:
            notes_lines.append(f"- {err}")
        if len(errors) > 50:
            notes_lines.append(f"- …ほか {len(errors) - 50} 件")

    with open(REPORT_MD, "w", encoding="utf-8") as f:
        sections: List[str] = summary_lines + ["\n### 指標の見方\n"] + column_guides + ["\n"] + table_lines
        if digest_lines:
            sections += ["\n"] + digest_lines
        sections += ["\n"] + notes_lines
        f.write("\n".join(sections))

    print("Saved:", REPORT_CSV, REPORT_MD)


if __name__ == "__main__":
    main()
