"""Generate a weekly summary of high-scoring screen results.

This script scans the `reports/` directory for daily screener CSV files
(`screen_YYYYMMDD.csv`), filters entries whose `score_0to7` meets or exceeds a
threshold, and writes a Markdown summary for the trailing 7-day window.

Usage (default: end date is today's date in JST)::

    python scripts/generate_weekly_summary.py

You can override the as-of date (in JST) and the number of days with CLI
options, which is helpful for backfilling or testing::

    python scripts/generate_weekly_summary.py --as-of-date 20251022 --days 7

The summary is saved to `reports/weekly_summary_YYYYMMDD.md` where the suffix is
the as-of date.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = REPO_ROOT / "reports"
OUTPUT_PREFIX = "weekly_summary"
DEFAULT_DAYS = 7
NEW_HIGH_MAX_SCORE = 7
NEW_HIGH_SCORE_THRESHOLD = 6
OFFICIAL_SCORE_RATIO_THRESHOLD = 0.75
JST = ZoneInfo("Asia/Tokyo")


@dataclass
class ScreenerRow:
    report_date: date
    symbol: str
    name_jp: str
    market: str
    score_new_high: int
    official_score: Optional[int]
    official_applicable: Optional[int]
    annual_last1_yoy: Optional[float]
    annual_last2_cagr: Optional[float]
    q_last_pretax_yoy: Optional[float]
    q_last_revenue_yoy: Optional[float]
    notes: str

    @classmethod
    def from_csv(cls, row: dict[str, str], report_date: date) -> "ScreenerRow":
        def parse_optional_float(value: str) -> Optional[float]:
            value = value.strip()
            if not value:
                return None
            try:
                return float(value)
            except ValueError:
                return None

        def parse_optional_int(value: str) -> Optional[int]:
            value = value.strip()
            if not value:
                return None
            try:
                return int(float(value))
            except ValueError:
                return None

        return cls(
            report_date=report_date,
            symbol=row.get("symbol", "").strip(),
            name_jp=row.get("name_jp", "").strip(),
            market=row.get("market", "").strip(),
            score_new_high=int(float(row.get("score_0to7", "0"))),
            official_score=parse_optional_int(row.get("official_score", "")),
            official_applicable=parse_optional_int(row.get("official_applicable", "")),
            annual_last1_yoy=parse_optional_float(row.get("annual_last1_yoy", "")),
            annual_last2_cagr=parse_optional_float(row.get("annual_last2_cagr", "")),
            q_last_pretax_yoy=parse_optional_float(row.get("q_last_pretax_yoy", "")),
            q_last_revenue_yoy=parse_optional_float(row.get("q_last_revenue_yoy", "")),
            notes=row.get("notes", "").strip(),
        )


@dataclass
class SummaryEntry:
    row: ScreenerRow
    score_value: float
    score_display: str

    def sort_key(self) -> tuple[float, date, str]:
        return (-self.score_value, self.row.report_date, self.row.symbol)


@dataclass
class SummaryResults:
    new_high: list[SummaryEntry]
    official: list[SummaryEntry]


def parse_report_date(path: Path) -> Optional[date]:
    stem = path.stem  # e.g. screen_20251022
    try:
        _, date_str = stem.split("_", 1)
    except ValueError:
        return None
    if len(date_str) != 8 or not date_str.isdigit():
        return None
    year = int(date_str[:4])
    month = int(date_str[4:6])
    day = int(date_str[6:])
    return date(year, month, day)


def iter_report_rows(paths: Iterable[Path]) -> Iterable[ScreenerRow]:
    for path in paths:
        report_date = parse_report_date(path)
        if report_date is None:
            continue
        with path.open(newline="", encoding="utf-8") as fp:
            reader = csv.DictReader(fp)
            for raw_row in reader:
                try:
                    row = ScreenerRow.from_csv(raw_row, report_date)
                except ValueError:
                    continue
                yield row


def format_percentage(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"


def _score_new_high(row: ScreenerRow) -> Optional[tuple[float, str]]:
    if row.score_new_high < NEW_HIGH_SCORE_THRESHOLD or NEW_HIGH_MAX_SCORE <= 0:
        return None
    ratio = row.score_new_high / NEW_HIGH_MAX_SCORE
    display = f"{row.score_new_high}/{NEW_HIGH_MAX_SCORE}"
    return ratio, display


def _score_official(row: ScreenerRow) -> Optional[tuple[float, str]]:
    if (
        row.official_score is None
        or row.official_applicable is None
        or row.official_applicable <= 0
    ):
        return None
    ratio = row.official_score / row.official_applicable
    if ratio < OFFICIAL_SCORE_RATIO_THRESHOLD:
        return None
    display = f"{row.official_score}/{row.official_applicable}"
    return ratio, display


def _select_best_entries(
    rows: list[ScreenerRow], score_fn
) -> list[SummaryEntry]:
    best_by_symbol: dict[str, SummaryEntry] = {}
    for row in rows:
        result = score_fn(row)
        if result is None:
            continue
        score_value, score_display = result
        candidate = SummaryEntry(row=row, score_value=score_value, score_display=score_display)
        existing = best_by_symbol.get(row.symbol)
        if existing is None:
            best_by_symbol[row.symbol] = candidate
            continue
        if candidate.score_value > existing.score_value or (
            candidate.score_value == existing.score_value
            and candidate.row.report_date > existing.row.report_date
        ):
            best_by_symbol[row.symbol] = candidate
    return sorted(best_by_symbol.values(), key=lambda entry: entry.sort_key())


def build_summary(entries: Iterable[ScreenerRow]) -> SummaryResults:
    rows = list(entries)
    return SummaryResults(
        new_high=_select_best_entries(rows, _score_new_high),
        official=_select_best_entries(rows, _score_official),
    )


def _render_section(
    title: str,
    entries: list[SummaryEntry],
    score_header: str,
) -> list[str]:
    lines: list[str] = []
    lines.append(f"## {title}")
    lines.append("")
    if not entries:
        lines.append("> 該当なし")
        lines.append("")
        return lines

    lines.append(
        f"|日付|Symbol|銘柄名|市場|{score_header}|直近1Y YoY|直近2Y CAGR|Q(pretax YoY)|Q(rev YoY)|メモ|"
    )
    lines.append("|---|---|---|---|---:|---:|---:|---:|---:|---|")
    for entry in entries:
        row = entry.row
        lines.append(
            "|{date}|{symbol}|{name}|{market}|{score}|{yoy1}|{cagr}|{pretax}|{rev}|{notes}|".format(
                date=row.report_date.isoformat(),
                symbol=row.symbol,
                name=row.name_jp or "—",
                market=row.market or "—",
                score=entry.score_display,
                yoy1=format_percentage(row.annual_last1_yoy),
                cagr=format_percentage(row.annual_last2_cagr),
                pretax=format_percentage(row.q_last_pretax_yoy),
                rev=format_percentage(row.q_last_revenue_yoy),
                notes=row.notes.replace("\n", " ") or "—",
            )
        )
    lines.append("")
    return lines


def write_summary(
    results: SummaryResults,
    as_of: date,
    window_start: date,
    output_path: Path,
) -> None:
    new_high_threshold_label = f"{NEW_HIGH_SCORE_THRESHOLD}/{NEW_HIGH_MAX_SCORE}"
    official_threshold_label = f"{int(OFFICIAL_SCORE_RATIO_THRESHOLD * 100)}%"
    lines: list[str] = []
    lines.append(f"# 週間ハイライト（{as_of.isoformat()} JSTまで）")
    lines.append("")
    lines.append(
        f"- 期間: {window_start.isoformat()} 〜 {as_of.isoformat()} (JST)"
    )
    lines.append(f"- 閾値（スコア（新高値））: {new_high_threshold_label}")
    lines.append(f"- 閾値（スコア（株の公式））: {official_threshold_label}")
    lines.append(f"- 抽出銘柄数（スコア（新高値））: {len(results.new_high)}")
    lines.append(f"- 抽出銘柄数（スコア（株の公式））: {len(results.official)}")
    lines.append("")

    lines.extend(
        _render_section(
            f"スコア（新高値）ハイライト（{new_high_threshold_label} 以上）",
            results.new_high,
            "スコア（新高値）",
        )
    )
    lines.extend(
        _render_section(
            f"スコア（株の公式）ハイライト（{official_threshold_label} 以上）",
            results.official,
            "スコア（株の公式）",
        )
    )
    lines.append(
        "※ 数値は日次スクリーナーのCSV出力を再掲したもので、四捨五入しています。"
    )

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def resolve_as_of_date(as_of_str: Optional[str]) -> date:
    if as_of_str:
        return datetime.strptime(as_of_str, "%Y%m%d").date()
    return datetime.now(JST).date()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--as-of-date",
        help="集計対象の基準日（JST, YYYYMMDD）。指定しない場合は当日。",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help="集計対象とする日数（当日含む）。デフォルトは7日間。",
    )
    args = parser.parse_args()

    as_of_date = resolve_as_of_date(args.as_of_date)
    window_start = as_of_date - timedelta(days=max(args.days - 1, 0))

    csv_paths = sorted(REPORTS_DIR.glob("screen_*.csv"))
    relevant_paths = [
        path
        for path in csv_paths
        if (report_date := parse_report_date(path))
        and window_start <= report_date <= as_of_date
    ]

    summary = build_summary(iter_report_rows(relevant_paths))

    output_filename = f"{OUTPUT_PREFIX}_{as_of_date.strftime('%Y%m%d')}.md"
    output_path = REPORTS_DIR / output_filename
    write_summary(summary, as_of_date, window_start, output_path)


if __name__ == "__main__":
    main()
