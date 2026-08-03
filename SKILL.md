---
name: opendata-skill
description: Comprehensive Open Data Fetcher optimized for SCM, Marketing, and Economic Analysis. Covers e-Stat, Yahoo Finance, Weather, Land Prices, RESAS, PLATEAU, World Bank, OECD, BOJ Tankan, Cabinet Office CI/DI, and more.
version: 2.2.1 (Robustness & JP Leading Indicators)
---

# 🌏 OpenData Skill (Professional Edition)

**"データドリブンな意思決定を、瞬時に。"**

このスキルは、世の中に散在するオープンデータや外部APIを、単一のクリーンで分析可能なインターフェース（`OpenDataHub`）に統合するツールキットです。
需要予測（Darts）やビジネス分析において、「外部要因（市況、天候、トレンド、地政学リスク）」をモデルに供給するための**データパイプラインの心臓部**として機能します。

データソースごとの仕様調査・認証方式の違い・エラーハンドリング・周波数の異なる系列の前処理といった付随作業を本スキルが一括して引き受けるため、呼び出し元のエージェントは「どのデータを、どう分析に活かすか」に集中できます。

---

## 🎯 主な利用シーン

- **需要予測モデルへの外生変数供給**: 気象・為替・コモディティ・景気動向指数などを、予測モデルにそのまま投入できる形式で取得する。
- **サプライチェーンリスクの定量把握**: 港湾混雑・地政学イベント・地震・山火事など、SC断絶リスクを構造化データとして継続的にモニタリングする。
- **マーケティング・商圏分析**: 検索トレンド・人口動態・地価情報などを組み合わせ、需要地域や出店計画を検討する。
- **業界別の先行指標モニタリング**: 日銀短観・PMI・半導体Book-to-Bill比など、業種ごとに有効性の高い先行指標を横断的に取得する。

産業別にどのデータソースが有効かは `references/INDUSTRY_GUIDE.md` に整理されている。ユースケースに悩む場合は先にこれを読むこと。

## 🚫 スコープ外（このスキルが担わない領域）

- 取得データの予測モデル化（`darts-forecast-skill` 等の責務）
- データ可視化・ダッシュボード生成（呼び出し側の責務）
- リアルタイムストリーミング（バッチ取得のみ）
- 取得データの長期蓄積・データウェアハウス化（`BigQuery` スキル等の責務）

これらを求められた場合は、本スキルでデータ取得までを行い、後続処理は適切な別スキルに委ねること。

---

## 🧠 Progressive Disclosure (When to use what)
推論スピードを最大化するため、取得可能なデータの詳細一覧や具体的なCLIコマンドは外部ファイルに分離（プログレッシブ開示）されている。**絶対にコマンドやデータ構造を推測しないこと。**

- **どんなデータ（経済、天候、トレンド等）が取得可能か、またその詳細を知りたい場合**は、必ず以下を読むこと。
  - `read_file("references/capabilities.md")`
- **スクリプトの実行方法、`OpenDataHub` の使い方、CLI引数を知りたい場合**は、必ず以下を読むこと。
  - `read_file("references/usage_guide.md")`
- **どの産業でどのデータソースが有効か知りたい場合**は、以下を読むこと。
  - `read_file("references/INDUSTRY_GUIDE.md")`
- **システム要件、機能一覧、非機能要件、制約条件を正確に知りたい場合**は、以下を読むこと。
  - `read_file("docs/REQUIREMENTS.md")`
- **各データソースの利用規約・出典表記・商用利用の制約を知りたい場合**は、以下を読むこと。
  - `read_file("docs/DATA_SOURCE_TERMS.md")`

---

## 🛠️ コア・アーキテクチャ (Core Principles)

- **Unified Interface**: `scripts/opendata_hub.py` の `OpenDataHub` が全フェッチャーを統括する唯一の統合ポイント。初期化時に `scripts/*_fetcher.py` を自動検出するため、新規ソースの追加は命名規則に従うだけで済み、手動のレジストリ登録は不要。各ソースは単体CLIとしても実行可能。
- **Polars First**: パフォーマンスとメモリ効率のため、内部データ処理の標準は `pandas` ではなく `polars` を採用している。
- **Fail Loud, Not Silent**: 取得失敗（パース失敗等）を「データ無し」と誤認させず、欠損covariateの混入を防ぐ。取得失敗が「確定した無データ」と区別されるよう常に扱うこと。退化データ（空・全null）はキャッシュしない。
- **Resilience**: 一時的エラー（HTTP 429/5xx・接続・タイムアウト）のみをリトライし、プログラムエラー（KeyError等）は即送出するリトライ層を標準装備している。無駄なリトライで待機時間を浪費しない設計。
- **Return-value First**: フェッチャーの戻り値DataFrameを優先消費し、CSV経由の型喪失（日付の文字列化）を回避する（`_fetch_to_df`）。
- **キャッシュ**: 取得済みデータはParquet形式でローカルキャッシュされ、TTLはソースの変動性に応じて調整される（天候/AIS/GDELTは数時間、市場データは半日〜1日、マクロ/貿易データは1週間〜1ヶ月）。
- **Parallel & Align**: `OpenDataHub.get_many()` で多ソースを並列取得し、`scripts/time_align.py` で異周波数の外生変数を共通周波数に揃えてからモデルに供給できる。1ソースの失敗は隔離され、他のソース取得を妨げない。

---

## 📜 License & Data Terms

本ソフトウェアは MIT License である（`LICENSE` 参照）。**取得したデータそのものの利用条件は、各データ提供元の規約に従う**（本ソフトウェアのライセンスとは別軸）。e-Stat / FRED / Open-Meteo には必須表記があり、Open-Meteo無償APIは非商用限定、yfinance/pytrendsは非公式・グレーゾーン、ODPTは開発者登録必須である。商用利用や出典表記が絡む提案を行う前に、必ず `docs/DATA_SOURCE_TERMS.md` を確認すること。
