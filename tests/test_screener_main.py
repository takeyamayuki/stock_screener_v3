from datetime import date

import pandas as pd

import scripts.screener as screener
from scripts.providers.models import AnnualRecord, CompanyInfo, QuarterlyRecord


class DummyProvider:
    def get_annual(self, symbol: str):
        return [
            AnnualRecord("2024", date(2024, 3, 31), 200, 60, None, None, "JPY", "kabutan"),
            AnnualRecord("2023", date(2023, 3, 31), 180, 40, None, None, "JPY", "kabutan"),
            AnnualRecord("2022", date(2022, 3, 31), 150, 30, None, None, "JPY", "kabutan"),
        ]

    def get_quarterly(self, symbol: str):
        return [
            QuarterlyRecord("2025Q2", date(2025, 6, 30), 70, 30, None, None, "JPY", "kabutan"),
            QuarterlyRecord("2025Q1", date(2025, 3, 31), 60, 20, None, None, "JPY", "kabutan"),
            QuarterlyRecord("2024Q4", date(2024, 12, 31), 55, 18, None, None, "JPY", "kabutan"),
            QuarterlyRecord("2024Q3", date(2024, 9, 30), 50, 16, None, None, "JPY", "kabutan"),
            QuarterlyRecord("2024Q2", date(2024, 6, 30), 45, 14, None, None, "JPY", "kabutan"),
        ]

    def get_company_info(self, symbol: str):
        return CompanyInfo(symbol, "テスト銘柄", "プライム", "東証Ｐ", "kabutan", per=25.0)


def test_perplexity_digest_success_and_failure(monkeypatch):
    monkeypatch.setattr(screener, "PPX_KEY", "key")

    class Response:
        def __init__(self, content: str):
            self._content = content

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": self._content}}]}

    monkeypatch.setattr(screener.requests, "post", lambda *_, **__: Response("要約"))
    assert screener.perplexity_digest("1234.T") == "要約"

    def raise_error(*_, **__):
        raise RuntimeError("network")

    monkeypatch.setattr(screener.requests, "post", raise_error)
    assert "失敗" in screener.perplexity_digest("1234.T")


def test_main_generates_reports(tmp_path, monkeypatch):
    symbols_path = tmp_path / "symbols.txt"
    symbols_path.write_text("1234.T\n", encoding="utf-8")

    csv_path = tmp_path / "screen_TEST.csv"
    md_path = tmp_path / "screen_TEST.md"

    monkeypatch.setattr(screener, "SYMBOLS_PATH", symbols_path)
    monkeypatch.setattr(screener, "REPORT_CSV", csv_path)
    monkeypatch.setattr(screener, "REPORT_MD", md_path)
    monkeypatch.setattr(screener, "FinancialDataProvider", lambda: DummyProvider())
    monkeypatch.setattr(screener, "perplexity_digest", lambda symbol: "サマリー")
    monkeypatch.setattr(
        screener,
        "official_checks",
        lambda *_: {
            "metrics": {
                "rule1_new_high": True,
                "rule3_growth": True,
                "rule3_no_decline": True,
                "rule4_recent20": True,
                "rule5_sales": True,
                "rule6_profit": True,
                "rule7_resilience": True,
                "rule8_per": True,
            },
            "applicable": screener.OFFICIAL_MAX_SCORE,
            "score": 6,
        },
    )
    monkeypatch.setattr(screener, "FINANCIAL_RETRY_DELAY", 0)
    monkeypatch.setattr(screener, "SYMBOL_DELAY_SECONDS", 0)

    screener.main()

    df = pd.read_csv(csv_path)
    assert df.loc[0, "name_jp"] == "テスト銘柄"
    assert df.loc[0, "score_0to7"] >= 4
    assert df.loc[0, "official_score"] >= 1
    assert "テスト銘柄" in md_path.read_text(encoding="utf-8")


def test_main_handles_empty_symbols(tmp_path, monkeypatch):
    symbols_path = tmp_path / "symbols.txt"
    symbols_path.write_text("\n", encoding="utf-8")
    csv_path = tmp_path / "screen_NONE.csv"
    md_path = tmp_path / "screen_NONE.md"

    monkeypatch.setattr(screener, "SYMBOLS_PATH", symbols_path)
    monkeypatch.setattr(screener, "REPORT_CSV", csv_path)
    monkeypatch.setattr(screener, "REPORT_MD", md_path)

    screener.main()

    assert csv_path.read_text(encoding="utf-8").strip() == ""
    assert "シンボルが0件" in md_path.read_text(encoding="utf-8")


def test_main_appends_note_when_official_applicable_is_low(tmp_path, monkeypatch):
    symbols_path = tmp_path / "symbols.txt"
    symbols_path.write_text("1234.T\n", encoding="utf-8")

    csv_path = tmp_path / "screen_TEST.csv"
    md_path = tmp_path / "screen_TEST.md"

    monkeypatch.setattr(screener, "SYMBOLS_PATH", symbols_path)
    monkeypatch.setattr(screener, "REPORT_CSV", csv_path)
    monkeypatch.setattr(screener, "REPORT_MD", md_path)
    monkeypatch.setattr(screener, "FinancialDataProvider", lambda: DummyProvider())
    monkeypatch.setattr(
        screener,
        "official_checks",
        lambda *_: {
            "metrics": {
                "rule1_new_high": True,
                "rule3_growth": True,
                "rule3_no_decline": True,
                "rule4_recent20": True,
                "rule5_sales": True,
                "rule6_profit": True,
                "rule7_resilience": True,
                "rule8_per": True,
            },
            "applicable": 4,
            "score": 4,
        },
    )
    monkeypatch.setattr(screener, "perplexity_digest", lambda symbol: "")
    monkeypatch.setattr(screener, "FINANCIAL_RETRY_DELAY", 0)
    monkeypatch.setattr(screener, "SYMBOL_DELAY_SECONDS", 0)

    screener.main()

    df = pd.read_csv(csv_path)
    assert "公式スコア上限4/8" in df.loc[0, "notes"]
