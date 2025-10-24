# JP 52-Week High Screener (No-Scrape)

- Perplexity API と株探ランキングを組み合わせ、東証プライム/スタンダード/グロースの52週高値銘柄を網羅的に取得（各市場20件を目標）
- Yahoo!ファイナンス日本版と株探の財務データを組み合わせて独自基準でスコアリング
- 銘柄名・市場区分・指標の説明を含む CSV/Markdown を reports/ に日次出力（JST 08:30）

## Setup

1. リポジトリにこの一式を配置
2. GitHub → Settings → Secrets and variables → Actions にキー追加
   - `PERPLEXITY_API_KEY`（任意：要約に使用）
3. Actionsタブ → **Run workflow** で手動起動（以降は毎朝自動）

## 調整ポイント
- 最大銘柄数：`.github/workflows/screener.yml` の `MAX_SYMBOLS`
- 市場ごとの取得目標数：`TARGET_PER_MARKET`（デフォルト20件）
- 取得リトライ：`FINANCIAL_RETRY_ATTEMPTS`（デフォルト1回）、リトライ間隔 `FINANCIAL_RETRY_DELAY`（秒）
- シンボル間のウェイト：`SYMBOL_DELAY_SECONDS`（デフォルト0秒）
- レート制限：`THROTTLE_SECONDS`（無料枠は ~5req/min、13–15秒推奨）
- 判定ロジック：`scripts/screener.py` の `annual_checks` / `quarterly_checks` / `score`

## 手動チェック用ワークフロー
- `fetch-symbols-test`: 手動起動で `fetch_symbols_ppx.py` を単体実行。`config/symbols.txt` がアーティファクトとして保存されるので、結果を目視確認できます。
- `screener-test`: 手動起動で `screener.py` を実行し、出力した `reports/screen_*.{csv,md}` をアーティファクト化。前段で生成した `config/symbols.txt` を使いたい場合は、同ワークフローの入力 `run_fetch_first` を `true` にしてください。

## 注意
- 日本の「経常利益」は Yahoo!ファイナンス／株探の公表値を利用。
- 52週高値の“一覧”はPerplexityの検索に依存（スクレイピング不要）。
- ETF/REIT 等は株探の市場区分（東証Ｐ/Ｓ/Ｇ以外）で除外。

## テストの実行

```
python -m pip install -r requirements-dev.txt
pytest
```
