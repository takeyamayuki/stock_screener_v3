# JP 52-Week High Screener (No-Scrape)

- Perplexity API で当日の「日本株 52週高値（P/S/G）」一覧を取得
- Alpha Vantage で財務（preTax/revenue）を取得し、独自基準でスコアリング
- CSV/Markdown を reports/ に日次出力（JST 08:30）

## Setup

1. リポジトリにこの一式を配置
2. GitHub → Settings → Secrets and variables → Actions にキー追加
   - `PERPLEXITY_API_KEY`（必須）
   - `ALPHAVANTAGE_KEY`（推奨：スクリーニング＆ETF除外確認に使用）
3. Actionsタブ → **Run workflow** で手動起動（以降は毎朝自動）

## 調整ポイント
- 最大銘柄数：`.github/workflows/screener.yml` の `MAX_SYMBOLS`
- レート制限：`THROTTLE_SECONDS`（無料枠は ~5req/min、13–15秒推奨）
- 判定ロジック：`scripts/screener.py` の `annual_checks` / `quarterly_checks` / `score`

## 注意
- 日本の「経常利益」に相当するAPI項目が無いので、**`incomeBeforeTax` を代替**として使用。
- 52週高値の“一覧”はPerplexityの検索に依存（スクレイピング不要）。
- ETF/REIT 等は Alpha Vantage `OVERVIEW.AssetType` の 7日キャッシュで極力除外。
