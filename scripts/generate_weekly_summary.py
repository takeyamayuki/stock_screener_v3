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
SCORE_THRESHOLD = 6
JST = ZoneInfo("Asia/Tokyo")


@dataclass
class ScreenerRow:
    report_date: date
    symbol: str
    name_jp: str
    market: str
    score: int
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

        return cls(
            report_date=report_date,
            symbol=row.get("symbol", "").strip(),
            name_jp=row.get("name_jp", "").strip(),
            market=row.get("market", "").strip(),
            score=int(float(row.get("score_0to7", "0"))),
            annual_last1_yoy=parse_optional_float(row.get("annual_last1_yoy", "")),
            annual_last2_cagr=parse_optional_float(row.get("annual_last2_cagr", "")),
            q_last_pretax_yoy=parse_optional_float(row.get("q_last_pretax_yoy", "")),
            q_last_revenue_yoy=parse_optional_float(row.get("q_last_revenue_yoy", "")),
            notes=row.get("notes", "").strip(),
        )


@dataclass
class SummaryEntry:
    row: ScreenerRow

    def sort_key(self) -> tuple[int, date, str]:
        return (-self.row.score, self.row.report_date, self.row.symbol)


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


def build_summary(entries: Iterable[ScreenerRow]) -> list[SummaryEntry]:
    best_by_symbol: dict[str, SummaryEntry] = {}
    for row in entries:
        if row.score < SCORE_THRESHOLD:
            continue
        existing = best_by_symbol.get(row.symbol)
        new_entry = SummaryEntry(row=row)
        if existing is None:
            best_by_symbol[row.symbol] = new_entry
            continue
        if new_entry.row.score > existing.row.score or (
            new_entry.row.score == existing.row.score
            and new_entry.row.report_date > existing.row.report_date
        ):
            best_by_symbol[row.symbol] = new_entry
    return sorted(best_by_symbol.values(), key=lambda entry: entry.sort_key())


def write_summary(
    entries: list[SummaryEntry],
    as_of: date,
    window_start: date,
    output_path: Path,
) -> None:
    lines: list[str] = []
    lines.append(f"# 週間ハイライト（{as_of.isoformat()} JSTまで）")
    lines.append("")
    lines.append(
        f"- 期間: {window_start.isoformat()} 〜 {as_of.isoformat()} (JST)"
    )
    lines.append(f"- スコア閾値: {SCORE_THRESHOLD}")
    lines.append(f"- 抽出銘柄数: {len(entries)}")
    lines.append("")

    if not entries:
        lines.append(
            "該当する銘柄はありませんでした。日次レポートのスコア推移を確認してください。"
        )
    else:
        lines.append(
            "|日付|Symbol|銘柄名|市場|Score|直近1Y YoY|直近2Y CAGR|Q(pretax YoY)|Q(rev YoY)|メモ|"
        )
        lines.append(
            "|---|---|---|---|---:|---:|---:|---:|---:|---|"
        )
        for entry in entries:
            row = entry.row
            lines.append(
                "|{date}|{symbol}|{name}|{market}|{score}|{yoy1}|{cagr}|{pretax}|{rev}|{notes}|".format(
                    date=row.report_date.isoformat(),
                    symbol=row.symbol,
                    name=row.name_jp or "—",
                    market=row.market or "—",
                    score=row.score,
                    yoy1=format_percentage(row.annual_last1_yoy),
                    cagr=format_percentage(row.annual_last2_cagr),
                    pretax=format_percentage(row.q_last_pretax_yoy),
                    rev=format_percentage(row.q_last_revenue_yoy),
                    notes=row.notes.replace("\n", " ") or "—",
                )
            )
    lines.append("")
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

    entries = build_summary(iter_report_rows(relevant_paths))

    output_filename = f"{OUTPUT_PREFIX}_{as_of_date.strftime('%Y%m%d')}.md"
    output_path = REPORTS_DIR / output_filename
    write_summary(entries, as_of_date, window_start, output_path)


if __name__ == "__main__":
    main()
