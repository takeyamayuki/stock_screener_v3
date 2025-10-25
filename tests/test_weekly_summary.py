from datetime import date
from pathlib import Path
import sys

import pytest

import scripts.generate_weekly_summary as weekly


def test_parse_report_date_and_format_percentage():
    path = Path("screen_20251022.csv")
    assert weekly.parse_report_date(path) == date(2025, 10, 22)
    assert weekly.parse_report_date(Path("invalid.csv")) is None
    assert weekly.parse_report_date(Path("screen_202510.csv")) is None
    assert weekly.format_percentage(0.1234) == "12.3%"
    assert weekly.format_percentage(None) == "—"


def test_build_summary_picks_best_score():
    rows = [
        weekly.ScreenerRow(date(2025, 10, 20), "AAA", "テスト", "プライム", 6, None, None, None, None, ""),
        weekly.ScreenerRow(date(2025, 10, 21), "AAA", "テスト", "プライム", 7, None, None, None, None, ""),
        weekly.ScreenerRow(date(2025, 10, 22), "BBB", "テスト2", "スタンダード", 5, None, None, None, None, ""),
    ]
    entries = weekly.build_summary(rows)
    assert [entry.row.symbol for entry in entries] == ["AAA"]
    assert entries[0].row.score == 7


def test_iter_report_rows_parses_csv(tmp_path, monkeypatch):
    reports_dir = tmp_path
    csv_path = reports_dir / "screen_20251022.csv"
    csv_path.write_text(
        "symbol,name_jp,market,score_0to7,annual_last1_yoy,annual_last2_cagr\n"
        "AAA,テスト,プライム,6,0.2,invalid\n",
        encoding="utf-8",
    )
    rows = list(weekly.iter_report_rows([csv_path]))
    assert rows[0].annual_last2_cagr is None


def write_csv(path: Path, rows: list[str]):
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_main_generates_markdown(tmp_path, monkeypatch):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    monkeypatch.setattr(weekly, "REPORTS_DIR", reports_dir)

    write_csv(
        reports_dir / "screen_20251020.csv",
        [
            "symbol,name_jp,market,score_0to7,annual_last1_yoy,annual_last2_cagr,q_last_pretax_yoy,q_last_revenue_yoy,notes",
            "AAA,テスト,プライム,6,0.2,0.3,0.4,0.5,好調",
        ],
    )
    write_csv(
        reports_dir / "screen_20251021.csv",
        [
            "symbol,name_jp,market,score_0to7,annual_last1_yoy,annual_last2_cagr,q_last_pretax_yoy,q_last_revenue_yoy,notes",
            "BBB,テスト2,スタンダード,7,0.1,0.2,0.3,0.4,注意",
        ],
    )

    monkeypatch.setattr(sys, "argv", ["generate_weekly_summary", "--as-of-date", "20251021", "--days", "2"])
    weekly.main()

    output = (reports_dir / "weekly_summary_20251021.md").read_text(encoding="utf-8")
    assert "週間ハイライト" in output
    assert "BBB" in output
