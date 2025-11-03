from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Iterable, List, Optional, Tuple

import pandas as pd
import requests
from dateutil import tz

try:  # pragma: no cover - allows running as script and as package
    from providers import CompanyInfo, FinancialDataProvider
except ImportError:  # pragma: no cover
    from .providers import CompanyInfo, FinancialDataProvider

PPX_KEY = os.environ.get("PERPLEXITY_API_KEY")
MAX_SYMBOLS = int(os.environ.get("MAX_SYMBOLS", "60"))
FINANCIAL_RETRY_ATTEMPTS = int(os.environ.get("FINANCIAL_RETRY_ATTEMPTS", "1"))
FINANCIAL_RETRY_DELAY = float(os.environ.get("FINANCIAL_RETRY_DELAY", "3"))
SYMBOL_DELAY_SECONDS = float(os.environ.get("SYMBOL_DELAY_SECONDS", "0"))

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
    no_decline_small = all(x >= -0.05 for x in yoy_series) if not yoy_series.empty else False
    avg_growth = float(yoy_series.mean()) if not yoy_series.empty else None
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
        "no_decline_small": no_decline_small,
        "avg_growth": avg_growth,
        "last1_yoy": last1,
        "last2_cagr": last2_cagr,
        "annual_df": df,
        "yoy_values": list(yoy_series),
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
        "recent_profit_yoy": [x if pd.notna(x) else None for x in last3["ordinary_yoy"].tolist()],
        "recent_revenue_yoy": [x if pd.notna(x) else None for x in last3["revenue_yoy"].tolist()],
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


def _valid_floats(values: Iterable) -> list[float]:
    """
    Filter out None and NaN values from the input iterable and return a list of floats.
    """
    return [x for x in values if x is not None and not pd.isna(x)]


def official_checks(
    annual_result: dict, quarterly_result: dict, info: Optional[CompanyInfo]
) -> dict:
    yoy_values = _valid_floats(annual_result.get("yoy_values", []))
    avg_growth = annual_result.get("avg_growth") if yoy_values else None
    rule1_new_high = True  # 入力銘柄は新高値ランキング由来
    rule3_growth = avg_growth is not None and avg_growth >= 0.07
    rule3_no_decline = None
    if yoy_values:
        rule3_no_decline = all(x >= -0.05 for x in yoy_values)
    last1_yoy = annual_result.get("last1_yoy")
    last2_cagr = annual_result.get("last2_cagr")
    rule4_recent20 = None
    if last1_yoy is not None and last2_cagr is not None:
        rule4_recent20 = last1_yoy >= 0.20 and last2_cagr >= 0.20
    recent_revenue = _valid_floats(quarterly_result.get("recent_revenue_yoy", []))
    recent_profit = _valid_floats(quarterly_result.get("recent_profit_yoy", []))
    rule5_sales = None
    if recent_revenue:
        rule5_sales = sum(1 for x in recent_revenue if x >= 0.10) >= 2
    rule6_profit = None
    if recent_profit:
        rule6_profit = sum(1 for x in recent_profit if x >= 0.20) >= 2
    rule7_resilience = None
    if recent_profit and yoy_values:
        rule7_resilience = all(x >= 0 for x in recent_profit[:3]) and all(x >= -0.05 for x in yoy_values[:3])
    per_ok = None
    if info and info.per is not None and not pd.isna(info.per):
        per_ok = info.per <= 60
    metrics = {
        "rule1_new_high": rule1_new_high,
        "rule3_growth": rule3_growth if avg_growth is not None else None,
        "rule3_no_decline": rule3_no_decline,
        "rule4_recent20": rule4_recent20,
        "rule5_sales": rule5_sales,
        "rule6_profit": rule6_profit,
        "rule7_resilience": rule7_resilience,
        "rule8_per": per_ok,
    }
    applicable = sum(1 for value in metrics.values() if value is not None)
    score = sum(1 for value in metrics.values() if value)
    return {
        "metrics": metrics,
        "applicable": applicable,
        "score": score,
        "avg_growth": avg_growth,
    }


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


def ratio(value: Optional[float], *, unit: str = "x") -> str:
    if value is None or pd.isna(value):
        return ""
    if unit:
        return f"{value:.1f}{unit}"
    return f"{value:.1f}"


def checkmark(value: Optional[bool]) -> str:
    if value is None:
        return "？"
    return "✅" if value else "—"


def fetch_financials(provider: FinancialDataProvider, symbol: str) -> Tuple[list, list]:
    attempts = FINANCIAL_RETRY_ATTEMPTS + 1
    last_annual: list = []
    last_quarterly: list = []
    for attempt in range(attempts):
        annual_records = provider.get_annual(symbol)
        quarterly_records = provider.get_quarterly(symbol)
        if annual_records or quarterly_records:
            return annual_records, quarterly_records
        last_annual, last_quarterly = annual_records, quarterly_records
        if FINANCIAL_RETRY_DELAY > 0 and attempt < attempts - 1:
            time.sleep(FINANCIAL_RETRY_DELAY)
    return last_annual, last_quarterly


def fetch_company_info(provider: FinancialDataProvider, symbol: str) -> Optional[CompanyInfo]:
    attempts = FINANCIAL_RETRY_ATTEMPTS + 1
    info: Optional[CompanyInfo] = None
    for attempt in range(attempts):
        info = provider.get_company_info(symbol)
        if info:
            return info
        if FINANCIAL_RETRY_DELAY > 0 and attempt < attempts - 1:
            time.sleep(FINANCIAL_RETRY_DELAY)
    return info


def compose_markdown(
    df: pd.DataFrame,
    errors: Iterable[str],
    num_input_symbols: int,
) -> str:
    summary_lines = [
        f"# 日次スクリーナー（{TODAY} JST）\n",
        "※ データ出典: Yahoo!ファイナンス / 株探（かぶたん）。\n",
        f"- 処理銘柄（表に掲載）: **{len(df)}** 件\n",
        f"- 入力シンボル数: {num_input_symbols} 件\n",
    ]

    column_guides = [
        "- `Symbol`: 東証ティッカー（例: 2726.T）。",
        "- `銘柄名`: Kabutanより取得した日本語正式名。",
        "- `市場`: 東証の市場区分（プライム/スタンダード/グロースなど）。",
        "- `Score`: 年次・四半期チェックの合計スコア（0〜7）。",
        "- `公式Score`: 株の公式ルールの達成数（適用可能な項目のみカウント）。",
        "- `PER`: Kabutanの現在PER（数値がない場合は空欄）。",
        "- `直近1Y YoY`: 直近通期の経常利益YoY（前年比）。",
        "- `直近2Y CAGR`: 直近2期の経常利益CAGR。",
        "- `Q(pretax YoY)`: 直近四半期の経常利益YoY。",
        "- `Q(rev YoY)`: 直近四半期の売上高YoY。",
        "- `メモ`: 未達項目や注意点のまとめ。",
        "- `新高値`: 株の公式 1。52週高値リスト由来か（原則✅）。",
        "- `年平均+7%`: 株の公式 3-1。過去の年平均成長率が7%以上か。",
        "- `減益なし`: 株の公式 3-2。過去5〜10年で大きな減益がないか。",
        "- `直近2Y+20%`: 株の公式 4。直近2期の経常CAGR/YoYが20%以上か。",
        "- `売上10%`: 株の公式 5。直近四半期で売上YoY+10%を複数回達成したか。",
        "- `利益20%`: 株の公式 6。直近四半期で経常YoY+20%を複数回達成したか。",
        "- `揺るぎない`: 株の公式 7。逆風下でも成長を維持しているか（減益なし & 直近Qでマイナスなし）。",
        "- `PER<=60`: 株の公式 8。株価収益率が足切り（60倍）以下か。",
        "- `業績安定`: 新高値ブレイク術 1。年次成長が5〜10%で安定しているか。",
        "- `大幅減益なし`: 新高値ブレイク術 1。途中で大幅減益がないか。",
        "- `直近1Y+20%`: 新高値ブレイク術 2。直近1年の経常利益が20%以上伸びたか。",
        "- `直近2Y+20%`: 新高値ブレイク術 2。直近2年のCAGRが20%以上か。",
        "- `直近Q基準`: 新高値ブレイク術 3。直近四半期で経常+20% & 売上+10%を満たしたか。",
        "- `連続クリア`: 新高値ブレイク術 3。直近2〜3四半期で基準を複数回達成したか。",
        "- `成長加速`: 新高値ブレイク術 3。経常YoYが加速しているか。",
        "- `利益率改善`: 新高値ブレイク術 4。経常利益率が前年同期比で改善しているか。",
        "※ `？` はデータ不足等で自動判定できない項目を示します。",
    ]

    digest_lines: List[str] = []
    if not df.empty:
        summary_table_lines = [
            "|Symbol|銘柄名|市場|Score|公式Score|PER|直近1Y YoY|直近2Y CAGR|Q(pretax YoY)|Q(rev YoY)|メモ|",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
        official_table_lines = [
            "|Symbol|新高値|年平均+7%|減益なし|直近2Y+20%|売上10%|利益20%|揺るぎない|PER<=60|",
            "|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
        ]
        breakout_table_lines = [
            "|Symbol|業績安定|大幅減益なし|直近1Y+20%|直近2Y+20%|直近Q基準|連続クリア|成長加速|利益率改善|",
            "|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
        ]
        for record in df.to_dict("records"):
            official_score_display = ""
            applicable = record.get("official_applicable")
            if applicable:
                official_score_display = f"{record.get('official_score', 0)}/{applicable}"
            summary_table_lines.append(
                f"|{record['symbol']}|{record.get('name_jp', '')}|{record.get('market', '')}|"
                f"{record.get('score_0to7', '')}|"
                f"{official_score_display}|"
                f"{ratio(record.get('per'), unit='')}|"
                f"{perc(record.get('annual_last1_yoy'))}|"
                f"{perc(record.get('annual_last2_cagr'))}|"
                f"{perc(record.get('q_last_pretax_yoy'))}|"
                f"{perc(record.get('q_last_revenue_yoy'))}|"
                f"{record.get('notes', '')}|"
            )
            official_table_lines.append(
                f"|{record['symbol']}|"
                f"{checkmark(record.get('official_rule1_new_high'))}|"
                f"{checkmark(record.get('official_rule3_growth'))}|"
                f"{checkmark(record.get('official_rule3_no_decline'))}|"
                f"{checkmark(record.get('official_rule4_recent20'))}|"
                f"{checkmark(record.get('official_rule5_sales'))}|"
                f"{checkmark(record.get('official_rule6_profit'))}|"
                f"{checkmark(record.get('official_rule7_resilience'))}|"
                f"{checkmark(record.get('official_rule8_per'))}|"
            )
            breakout_table_lines.append(
                f"|{record['symbol']}|"
                f"{checkmark(record.get('nh_stable_growth'))}|"
                f"{checkmark(record.get('nh_no_big_drop'))}|"
                f"{checkmark(record.get('nh_last1_20'))}|"
                f"{checkmark(record.get('nh_last2_20'))}|"
                f"{'✅' if record.get('q_last_ok_20_10') else '—'}|"
                f"{'✅' if record.get('q_seq_ok') else '—'}|"
                f"{'✅' if record.get('q_accelerating') else '—'}|"
                f"{'✅' if record.get('q_improving_margin') else '—'}|"
            )
            if record.get("digest"):
                digest_lines.append(f"**{record['symbol']} 要約**\n\n{record['digest']}\n")
    else:
        summary_table_lines = ["> 表示可能なデータがありませんでした。"]
        official_table_lines = []
        breakout_table_lines = []

    notes_lines: List[str] = []
    errors = list(errors)
    if errors:
        notes_lines.append("\n### 注記（処理できなかった銘柄など）\n")
        for err in errors[:50]:
            notes_lines.append(f"- {err}")
        if len(errors) > 50:
            notes_lines.append(f"- …ほか {len(errors) - 50} 件")

    sections: List[str] = (
        summary_lines
        + ["\n### 指標の見方\n"]
        + column_guides
        + ["\n### サマリー\n"]
        + summary_table_lines
    )
    if official_table_lines:
        sections += ["\n### 株の公式の基準（買い）\n"] + official_table_lines
    if breakout_table_lines:
        sections += ["\n### 新高値ブレイク投資術の基準（買い）\n"] + breakout_table_lines
    if digest_lines:
        sections += ["\n"] + digest_lines
    sections += ["\n"] + notes_lines
    return "\n".join(sections)


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
            annual_records, quarterly_records = fetch_financials(provider, symbol)
            if not annual_records and not quarterly_records:
                errors.append(f"{symbol}: financial data unavailable after retries")
                continue

            annual_df = to_dataframe(annual_records, "ordinary_income", "revenue")
            quarterly_df = to_dataframe(quarterly_records, "ordinary_income", "revenue")

            annual_result = annual_checks(annual_df)
            quarterly_result = quarterly_checks(quarterly_df)

            sc, notes = score(annual_result, quarterly_result)
            info = fetch_company_info(provider, symbol)
            official_result = official_checks(annual_result, quarterly_result, info)
            official_metrics = official_result["metrics"]

            note_parts = [part for part in notes.split("; ") if part]
            official_note_map = {
                "rule3_growth": "年平均成長+7%未達",
                "rule3_no_decline": "過去に減益あり",
                "rule4_recent20": "直近2年+20%未達",
                "rule5_sales": "売上YoY+10%不足",
                "rule6_profit": "経常YoY+20%不足",
                "rule7_resilience": "揺るぎない成長要件未満",
                "rule8_per": "PER>60",
            }
            for key, message in official_note_map.items():
                value = official_metrics.get(key)
                if value is False:
                    note_parts.append(message)
            notes = "; ".join(note_parts)

            last1 = annual_result.get("last1_yoy")
            last2 = annual_result.get("last2_cagr")
            lastQ = (
                quarterly_result.get("quarterly_df").iloc[0]
                if quarterly_result.get("enough_quarters") and quarterly_result.get("quarterly_df") is not None
                else None
            )
            lastQ_pre_yoy = None if lastQ is None else lastQ.get("ordinary_yoy")
            lastQ_rev_yoy = None if lastQ is None else lastQ.get("revenue_yoy")
            stable_flag = annual_result.get("stable_5_10")
            no_big_drop_flag = annual_result.get("no_big_drop")
            if not annual_result.get("enough_years"):
                stable_flag = None
                no_big_drop_flag = None
            last1_flag = None
            if last1 is not None and not pd.isna(last1):
                last1_flag = last1 >= 0.20
            last2_flag = None
            if last2 is not None and not pd.isna(last2):
                last2_flag = last2 >= 0.20

            rows.append(
                {
                    "symbol": symbol,
                    "name_jp": info.name if info else "",
                    "market": info.market if info else "",
                    "score_0to7": sc,
                    "official_score": official_result.get("score"),
                    "official_applicable": official_result.get("applicable"),
                    "official_rule1_new_high": official_metrics.get("rule1_new_high"),
                    "official_rule3_growth": official_metrics.get("rule3_growth"),
                    "official_rule3_no_decline": official_metrics.get("rule3_no_decline"),
                    "official_rule4_recent20": official_metrics.get("rule4_recent20"),
                    "official_rule5_sales": official_metrics.get("rule5_sales"),
                    "official_rule6_profit": official_metrics.get("rule6_profit"),
                    "official_rule7_resilience": official_metrics.get("rule7_resilience"),
                    "official_rule8_per": official_metrics.get("rule8_per"),
                    "nh_stable_growth": stable_flag,
                    "nh_no_big_drop": no_big_drop_flag,
                    "nh_last1_20": last1_flag,
                    "nh_last2_20": last2_flag,
                    "annual_last1_yoy": last1,
                    "annual_last2_cagr": last2,
                    "q_last_pretax_yoy": lastQ_pre_yoy,
                    "q_last_revenue_yoy": lastQ_rev_yoy,
                    "q_last_ok_20_10": quarterly_result.get("lastQ_ok"),
                    "q_seq_ok": quarterly_result.get("sequential_ok"),
                    "q_accelerating": quarterly_result.get("accelerating"),
                    "q_improving_margin": quarterly_result.get("improving_margin"),
                    "notes": notes,
                    "per": info.per if info else None,
                    "digest": perplexity_digest(symbol) if sc >= 3 else "",
                }
            )
        except Exception as exc:
            errors.append(f"{symbol}: {exc}")
        finally:
            if SYMBOL_DELAY_SECONDS > 0:
                time.sleep(SYMBOL_DELAY_SECONDS)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["score_0to7", "symbol"], ascending=[False, True])
    df.to_csv(REPORT_CSV, index=False, encoding="utf-8")

    markdown = compose_markdown(df, errors, len(symbols))
    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write(markdown)

    print("Saved:", REPORT_CSV, REPORT_MD)


if __name__ == "__main__":
    main()
