import pandas as pd

from scripts import screener


def test_compose_markdown_includes_table_and_digest():
    df = pd.DataFrame(
        [
            {
                "symbol": "1234.T",
                "name_jp": "テスト株式会社",
                "market": "プライム",
                "score_0to7": 5,
                "official_score": 6,
                "official_applicable": 7,
                "official_rule1_new_high": True,
                "official_rule3_growth": True,
                "official_rule3_no_decline": True,
                "official_rule4_recent20": True,
                "official_rule5_sales": True,
                "official_rule6_profit": True,
                "official_rule7_resilience": True,
                "official_rule8_per": True,
                "annual_last1_yoy": 0.25,
                "annual_last2_cagr": 0.22,
                "q_last_pretax_yoy": 0.3,
                "q_last_revenue_yoy": 0.15,
                "q_last_ok_20_10": True,
                "q_seq_ok": True,
                "q_accelerating": False,
                "q_improving_margin": True,
                "notes": "テストノート",
                "digest": "サンプル要約",
                "per": 28.0,
            }
        ]
    )

    markdown = screener.compose_markdown(df, errors=[], num_input_symbols=1)

    assert "|Symbol|銘柄名|市場|Score|公式Score|" in markdown
    assert "|1234.T|テスト株式会社|プライム|5|" in markdown
    assert "**1234.T 要約**" in markdown
    assert "サンプル要約" in markdown
    assert "### 指標の見方" in markdown


def test_compose_markdown_includes_error_section():
    df = pd.DataFrame(columns=["symbol"])
    markdown = screener.compose_markdown(df, errors=["foo: error"], num_input_symbols=3)
    assert "> 表示可能なデータがありませんでした。" in markdown
    assert "foo: error" in markdown
