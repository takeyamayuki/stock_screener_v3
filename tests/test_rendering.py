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
                "nh_stable_growth": True,
                "nh_no_big_drop": True,
                "nh_last1_20": True,
                "nh_last2_20": True,
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
                "market_strength_ratio": 0.1,
            }
        ]
    )

    markdown = screener.compose_markdown(df, errors=[], num_input_symbols=1)

    assert "### 株の公式の基準（買い）" in markdown
    assert "### 新高値ブレイク投資術の基準（買い）" in markdown
    assert "|Symbol|銘柄名|市場|スコア（新高値）|スコア（株の公式）|PER|" in markdown
    assert "|株の公式|" in markdown
    assert "|新高値ブレイク|" in markdown
    assert "|1234.T|テスト株式会社|プライム|5/7|6/8|28.0|" in markdown
    assert "強い: 増やす (10.0%)" in markdown
    assert "**1234.T 要約**" in markdown
    assert "サンプル要約" in markdown
    assert "### 指標の見方" in markdown


def test_compose_markdown_omits_error_notes():
    df = pd.DataFrame(columns=["symbol"])
    markdown = screener.compose_markdown(df, errors=["foo: error"], num_input_symbols=3)
    assert "> 表示可能なデータがありませんでした。" in markdown
    assert "foo: error" not in markdown
    assert "注記" not in markdown


def test_compose_markdown_hides_perplexity_failures():
    df = pd.DataFrame(
        [
            {
                "symbol": "9999.T",
                "name_jp": "テスト",
                "market": "P",
                "score_0to7": 3,
                "official_score": 2,
                "official_applicable": 2,
                "digest": "(Perplexity要約失敗: 401)",
            }
        ]
    )
    markdown = screener.compose_markdown(df, errors=[], num_input_symbols=1)
    assert "(Perplexity要約失敗" not in markdown
    assert "注記" not in markdown
