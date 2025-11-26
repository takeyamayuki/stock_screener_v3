from datetime import date
from pathlib import Path

import pandas as pd

import scripts.screener_us as screener_us
from scripts.providers.models import AnnualRecord, CompanyInfo, QuarterlyRecord


class DummyUSProvider:
    def get_annual(self, symbol: str):
        return [
            AnnualRecord("2024", date(2024, 12, 31), 200, 400, None, None, "USD", "dummy"),
            AnnualRecord("2023", date(2023, 12, 31), 150, 300, None, None, "USD", "dummy"),
            AnnualRecord("2022", date(2022, 12, 31), 120, 250, None, None, "USD", "dummy"),
        ]

    def get_quarterly(self, symbol: str):
        return [
            QuarterlyRecord("2025Q2", date(2025, 6, 30), 60, 120, None, None, "USD", "dummy"),
            QuarterlyRecord("2025Q1", date(2025, 3, 31), 55, 110, None, None, "USD", "dummy"),
            QuarterlyRecord("2024Q4", date(2024, 12, 31), 50, 100, None, None, "USD", "dummy"),
            QuarterlyRecord("2024Q3", date(2024, 9, 30), 45, 90, None, None, "USD", "dummy"),
            QuarterlyRecord("2024Q2", date(2024, 6, 30), 40, 80, None, None, "USD", "dummy"),
        ]

    def get_company_info(self, symbol: str):
        return CompanyInfo(symbol, "Test US", "NASDAQ", "NASDAQ", "dummy", per=20.0)


def test_screener_us_generates_reports(tmp_path, monkeypatch):
    symbols_path = tmp_path / "symbols_us.txt"
    symbols_path.write_text("AAPL\n", encoding="utf-8")

    csv_path = tmp_path / "reports" / "us" / "screen_us_TEST.csv"
    md_path = tmp_path / "reports" / "us" / "screen_us_TEST.md"
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(screener_us.base, "SYMBOLS_PATH", symbols_path)
    monkeypatch.setattr(screener_us.base, "REPORT_CSV", csv_path)
    monkeypatch.setattr(screener_us.base, "REPORT_MD", md_path)
    monkeypatch.setattr(screener_us, "AlphaVantageUS", lambda: DummyUSProvider())
    monkeypatch.setattr(screener_us.base, "FinancialDataProvider", DummyUSProvider)
    monkeypatch.setattr(screener_us.base, "FINANCIAL_RETRY_DELAY", 0)
    monkeypatch.setattr(screener_us.base, "SYMBOL_DELAY_SECONDS", 0)
    monkeypatch.setattr(screener_us.base, "perplexity_digest", lambda symbol: "")
    monkeypatch.setattr(screener_us.base, "OFFICIAL_MAX_SCORE", 8)
    monkeypatch.setattr(
        screener_us.base,
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
            "applicable": 8,
            "score": 6,
        },
    )

    screener_us.main()

    df = pd.read_csv(csv_path)
    assert df.loc[0, "symbol"] == "AAPL"
    assert "Test US" in md_path.read_text(encoding="utf-8")
