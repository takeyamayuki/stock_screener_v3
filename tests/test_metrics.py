import pandas as pd
import pytest

from scripts import screener


def test_annual_checks_basic_growth():
    df = pd.DataFrame(
        {
            "ordinary_income": [120, 100, 80, 80],
            "revenue": [300, 280, 250, 200],
            "period": ["2024", "2023", "2022", "2021"],
            "end_date": pd.to_datetime(["2024-03-31", "2023-03-31", "2022-03-31", "2021-03-31"]),
        }
    )

    results = screener.annual_checks(df)

    assert results["enough_years"] is True
    assert results["last1_yoy"] == pytest.approx(0.2)
    assert results["last2_cagr"] == pytest.approx((120 / 80) ** (1 / 2) - 1)
    assert results["no_big_drop"] is True
    assert results["no_decline_small"] is True
    assert results["avg_growth"] == pytest.approx(0.15)
    assert results["yoy_values"][0] == pytest.approx(0.2)


def test_annual_checks_empty_dataframe():
    df = pd.DataFrame(columns=["ordinary_income", "revenue"])
    results = screener.annual_checks(df)
    assert results == {"enough_years": False}


def test_quarterly_checks_triggers_and_flags():
    base = pd.DataFrame(
        {
            "ordinary_income": [260, 230, 210, 190, 200, 180, 160, 140],
            "revenue": [520, 460, 420, 380, 400, 360, 320, 280],
            "period": [
                "2025Q4",
                "2025Q3",
                "2025Q2",
                "2025Q1",
                "2024Q4",
                "2024Q3",
                "2024Q2",
                "2024Q1",
            ],
            "end_date": pd.to_datetime(
                [
                    "2025-12-31",
                    "2025-09-30",
                    "2025-06-30",
                    "2025-03-31",
                    "2024-12-31",
                    "2024-09-30",
                    "2024-06-30",
                    "2024-03-31",
                ]
            ),
        }
    )
    results = screener.quarterly_checks(base)

    assert results["enough_quarters"] is True
    assert results["lastQ_ok"] is True
    assert results["sequential_ok"] is True
    assert results["accelerating"] is True
    assert results["improving_margin"] is True
    assert len([x for x in results["recent_profit_yoy"] if x is not None]) == 3
    assert len([x for x in results["recent_revenue_yoy"] if x is not None]) == 3


def test_quarterly_checks_empty_dataframe():
    df = pd.DataFrame(columns=["ordinary_income", "revenue"])
    results = screener.quarterly_checks(df)
    assert results == {"enough_quarters": False}


def test_score_accumulates_hits_and_notes():
    annual_df = pd.DataFrame(
        {
            "ordinary_income": [150, 110, 80],
            "revenue": [240, 200, 160],
            "period": ["2024", "2023", "2022"],
            "end_date": pd.to_datetime(["2024-03-31", "2023-03-31", "2022-03-31"]),
        }
    )
    quarterly_df = pd.DataFrame(
        {
            "ordinary_income": [36, 30, 28, 26, 24, 22, 20, 18],
            "revenue": [72, 60, 56, 52, 48, 44, 40, 36],
            "period": [
                "2025Q4",
                "2025Q3",
                "2025Q2",
                "2025Q1",
                "2024Q4",
                "2024Q3",
                "2024Q2",
                "2024Q1",
            ],
            "end_date": pd.to_datetime(
                [
                    "2025-12-31",
                    "2025-09-30",
                    "2025-06-30",
                    "2025-03-31",
                    "2024-12-31",
                    "2024-09-30",
                    "2024-06-30",
                    "2024-03-31",
                ]
            ),
        }
    )

    annual_result = screener.annual_checks(annual_df)
    quarterly_result = screener.quarterly_checks(quarterly_df)
    score, notes = screener.score(annual_result, quarterly_result)

    assert score == 7
    assert "年率5–10%の安定成長は未達" in notes
    assert "直近Q: 経常+20% & 売上+10% 未達" not in notes


def test_score_handles_missing_sections():
    score, notes = screener.score({"enough_years": False}, {"enough_quarters": False})
    assert score == 0
    assert "年次データ不足" in notes
    assert "四半期データ不足" in notes


def test_perc_handles_none_and_numbers():
    assert screener.perc(None) == ""
    assert screener.perc(float("nan")) == ""
    assert screener.perc(0.1234) == "12.3%"


def test_official_checks_scores_rules():
    annual_df = pd.DataFrame(
        {
            "ordinary_income": [150, 120, 100, 90, 80],
            "revenue": [300, 260, 240, 220, 200],
            "period": ["2024", "2023", "2022", "2021", "2020"],
            "end_date": pd.to_datetime(
                ["2024-03-31", "2023-03-31", "2022-03-31", "2021-03-31", "2020-03-31"]
            ),
        }
    )
    quarterly_df = pd.DataFrame(
        {
            "ordinary_income": [40, 32, 28, 24, 22, 20, 18, 16],
            "revenue": [80, 64, 56, 48, 44, 40, 36, 32],
            "period": [
                "2025Q4",
                "2025Q3",
                "2025Q2",
                "2025Q1",
                "2024Q4",
                "2024Q3",
                "2024Q2",
                "2024Q1",
            ],
            "end_date": pd.to_datetime(
                [
                    "2025-12-31",
                    "2025-09-30",
                    "2025-06-30",
                    "2025-03-31",
                    "2024-12-31",
                    "2024-09-30",
                    "2024-06-30",
                    "2024-03-31",
                ]
            ),
        }
    )

    annual_result = screener.annual_checks(annual_df)
    quarterly_result = screener.quarterly_checks(quarterly_df)
    info = screener.CompanyInfo("1234.T", "テスト", "プライム", "東証Ｐ", "kabutan", per=25.0)

    official = screener.official_checks(annual_result, quarterly_result, info)

    assert official["score"] >= 5
    assert official["metrics"]["rule8_per"] is True
    assert official["metrics"]["rule5_sales"] is True
