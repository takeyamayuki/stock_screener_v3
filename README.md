# JP 52-Week High Screener (No-Scrape)

- 株探「本日52週高値を更新」ランキングをスクレイピングし、東証プライム/スタンダード/グロースの候補を収集（各市場20件を目標）
- Yahoo!ファイナンス日本版と株探の財務データを統合して独自スコアを算出
- 日次スクリーン（CSV/Markdown）を `reports/` へ出力し、週次サマリーも自動生成

## セットアップ

1. リポジトリをクローン（または GitHub Codespaces 等で開く）
2. 依存パッケージをインストール
   ```bash
   python -m pip install -U pip
   pip install -r requirements.txt
   ```
   開発・テスト用途では `pip install -r requirements-dev.txt` を追加実行してください。
3. 必要な環境変数を設定
   - `ALPHAVANTAGE_KEY`（必須：財務データ取得に利用）
   - `PERPLEXITY_API_KEY`（任意：要約生成に利用）

### ローカルでの実行手順

1. シンボルリストの取得  
   ```bash
   export ALPHAVANTAGE_KEY=...
   python scripts/fetch_symbols_ppx.py
   ```  
   `config/symbols.txt` が上書きされます。

2. スクリーナーの実行  
   ```bash
   export THROTTLE_SECONDS=13
   export MAX_SYMBOLS=60
   export ALPHAVANTAGE_MAX_DAILY_CALLS=20
   python scripts/screener.py
   ```  
   `reports/screen_YYYYMMDD.{csv,md}` が生成されます。

3. 週次サマリーの生成（任意）  
   ```bash
   python scripts/generate_weekly_summary.py --as-of-date YYYYMMDD
   ```  
   直近数日分の結果から `reports/weekly_summary_YYYYMMDD.md` を作成します。

## GitHub Actions ワークフロー

- `daily-stock-screen`（`.github/workflows/screener.yml`）  
  - JST 08:30 に実行。株探のランキングからシンボル取得→スクリーナー→`reports/` の差分をコミット。
  - `MAX_SYMBOLS` や `THROTTLE_SECONDS` などの実行パラメータはジョブ内の環境変数で管理。
- `run-tests`（`.github/workflows/tests.yml`）  
  - `main` への push / Pull Request / 手動実行で `pytest` を自動実行し、ユニットテストを常時検証。
- `weekly-highlights`（`.github/workflows/weekly-summary.yml`）  
  - 毎週土曜 00:30 JST（UTC 金曜 15:30）に週次ハイライトを生成し、差分があればコミット。
- 手動検証用ワークフロー  
  - `fetch-symbols-test`：`workflow_dispatch` のみで起動。`scripts/fetch_symbols_ppx.py` を単体実行し、生成した `config/symbols.txt` をアーティファクト化。  
    株探側のレイアウト変更や取得件数の異常が疑われる際、パラメータ変更の効果を確認したい際などにスポットで利用。
  - `screener-test`：`workflow_dispatch` のみで起動。必要に応じて前段の fetch を含めた `scripts/screener.py` の通し実行とレポート出力を確認。  
    スクリーナー全体の動作を GitHub Actions 上で再現したいとき（依存パッケージ更新後の確認、環境差異の切り分け等）に利用。

## 調整可能なパラメータ

- `.github/workflows/screener.yml` の `MAX_SYMBOLS`、`THROTTLE_SECONDS`
- `scripts/fetch_symbols_ppx.py` の `TARGET_PER_MARKET`
- 財務データのリトライ回数：`FINANCIAL_RETRY_ATTEMPTS`（遅延は `FINANCIAL_RETRY_DELAY` 秒）
- シンボル間ウェイト：`SYMBOL_DELAY_SECONDS`
- 判定ロジック：`scripts/screener.py` の `annual_checks` / `quarterly_checks` / `score`

## 注意点

- 財務指標は Yahoo!ファイナンス／株探の公開値を利用し、ETF/REIT 等は市場区分でフィルタ。
- 52週高値候補の一覧抽出は株探のランキングをスクレイピングして取得。
- API レート制限に留意し、無料枠の場合は 13–15 秒のスロットルを維持することを推奨。

## テスト

1. 依存関係  
   ```bash
   pip install -r requirements-dev.txt
   ```
2. テスト実行  
   ```bash
   pytest
   ```
3. カバレッジ計測（主要モジュールは `scripts/` 配下）  
   ```bash
   pytest --cov=scripts --cov-report=term-missing
   ```

主なテスト範囲：
- `tests/test_fetch_symbols.py`：株探ランキングのスクレイピング結果整形と重複排除
- `tests/test_kabutan_provider.py` / `tests/test_yahoo_provider.py`：財務データプロバイダのパースとエラー処理
- `tests/test_aggregator.py` / `tests/test_metrics.py`：スコアリング集計と補助指標計算
- `tests/test_weekly_summary.py`：`generate_weekly_summary.py` のレポート統合と Markdown 出力
- `tests/test_screener_main.py` ほか：CLI エントリポイントとレンダリングの統合挙動
