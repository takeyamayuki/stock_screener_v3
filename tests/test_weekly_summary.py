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


def make_row(
    report_date,
    symbol,
    score_new_high,
    official_score=None,
    official_applicable=None,
    market_cap=None,
):
    return weekly.ScreenerRow(
        report_date=report_date,
        symbol=symbol,
        name_jp="テスト",
        market="プライム",
        market_cap=market_cap,
        score_new_high=score_new_high,
        official_score=official_score,
        official_applicable=official_applicable,
        annual_last1_yoy=None,
        annual_last2_cagr=None,
        q_last_pretax_yoy=None,
        q_last_revenue_yoy=None,
        notes="",
    )


def test_build_summary_picks_best_score():
    rows = [
        make_row(date(2025, 10, 20), "AAA", 6, 5, 8),
        make_row(date(2025, 10, 21), "AAA", 7, 6, 8),
        make_row(date(2025, 10, 22), "BBB", 5, 7, 8),
    ]
    results = weekly.build_summary(rows)
    assert results == []


def test_iter_report_rows_parses_csv(tmp_path, monkeypatch):
    reports_dir = tmp_path
    csv_path = reports_dir / "screen_20251022.csv"
    csv_path.write_text(
        "symbol,name_jp,market,market_cap,score_0to7,official_score,official_applicable,annual_last1_yoy,annual_last2_cagr\n"
        "AAA,テスト,プライム,12345000000,6,5,8,0.2,invalid\n",
        encoding="utf-8",
    )
    rows = list(weekly.iter_report_rows([csv_path]))
    assert rows[0].market_cap == 12345000000
    assert rows[0].annual_last2_cagr is None
    assert rows[0].official_score == 5
    assert rows[0].official_applicable == 8


def write_csv(path: Path, rows: list[str]):
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_main_generates_markdown(tmp_path, monkeypatch):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    monkeypatch.setattr(weekly, "REPORTS_DIR", reports_dir)

    write_csv(
        reports_dir / "screen_20251020.csv",
        [
            "symbol,name_jp,market,market_cap,score_0to7,official_score,official_applicable,annual_last1_yoy,annual_last2_cagr,q_last_pretax_yoy,q_last_revenue_yoy,notes",
            "AAA,テスト,プライム,10000000000,6,9,9,0.2,0.3,0.4,0.5,好調",
        ],
    )
    write_csv(
        reports_dir / "screen_20251021.csv",
        [
            "symbol,name_jp,market,market_cap,score_0to7,official_score,official_applicable,annual_last1_yoy,annual_last2_cagr,q_last_pretax_yoy,q_last_revenue_yoy,notes",
            "BBB,テスト2,スタンダード,20000000000,7,9,9,0.1,0.2,0.3,0.4,注意",
        ],
    )

    monkeypatch.setattr(sys, "argv", ["generate_weekly_summary", "--as-of-date", "20251021", "--days", "2"])
    weekly.main()

    output = (reports_dir / "weekly_summary_20251021.md").read_text(encoding="utf-8")
    assert "週間ハイライト" in output
    assert "|日付|Symbol|銘柄名|市場|時価総額|スコア（新高値）|スコア（株の公式）|" in output
    assert "7/7" in output
    assert "9/9" in output
    assert "BBB" in output
    assert "|200億|" in output


def test_build_summary_sorts_by_total_score():
    rows = [
        make_row(date(2025, 10, 20), "AAA", 6, 9, 9),
        make_row(date(2025, 10, 21), "BBB", 7, 9, 9),
    ]
    results = weekly.build_summary(rows)
    assert [entry.row.symbol for entry in results] == ["BBB", "AAA"]
    assert results[0].total_score == 16  # 7 + 9
    assert results[1].total_score == 15  # 6 + 9
