# JP 52-Week High Screener (No-Scrape)

- Perplexity API で当日の「日本株 52週高値（P/S/G）」一覧を取得
- Yahoo!ファイナンス日本版と株探の財務データを組み合わせて独自基準でスコアリング
- CSV/Markdown を reports/ に日次出力（JST 08:30）

## Setup

1. リポジトリにこの一式を配置
2. GitHub → Settings → Secrets and variables → Actions にキー追加
   - `PERPLEXITY_API_KEY`（任意：要約に使用）
3. Actionsタブ → **Run workflow** で手動起動（以降は毎朝自動）

## 調整ポイント
- 最大銘柄数：`.github/workflows/screener.yml` の `MAX_SYMBOLS`
- レート制限：`THROTTLE_SECONDS`（無料枠は ~5req/min、13–15秒推奨）
- 判定ロジック：`scripts/screener.py` の `annual_checks` / `quarterly_checks` / `score`

## 手動チェック用ワークフロー
- `fetch-symbols-test`: 手動起動で `fetch_symbols_ppx.py` を単体実行。`config/symbols.txt` がアーティファクトとして保存されるので、結果を目視確認できます。
- `screener-test`: 手動起動で `screener.py` を実行し、出力した `reports/screen_*.{csv,md}` をアーティファクト化。前段で生成した `config/symbols.txt` を使いたい場合は、同ワークフローの入力 `run_fetch_first` を `true` にしてください。

## 注意
- 日本の「経常利益」は Yahoo!ファイナンス／株探の公表値を利用。
- 52週高値の“一覧”はPerplexityの検索に依存（スクレイピング不要）。
- ETF/REIT 等は Yahoo!ファイナンス `priceBoard.stockType` で除外。
