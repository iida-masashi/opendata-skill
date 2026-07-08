---
name: opendata-skill
description: Comprehensive Open Data Fetcher optimized for SCM, Marketing, and Economic Analysis. Covers e-Stat, Yahoo Finance, Weather, Land Prices, RESAS, PLATEAU, World Bank, OECD, BOJ Tankan, Cabinet Office CI/DI, and more.
version: 2.2.0 (Robustness & JP Leading Indicators)
---

# 🌏 OpenData Skill (Professional Edition)

**"データドリブンな意思決定を、瞬時に。"**

このスキルは、世の中に散在するオープンデータや外部APIを、単一のクリーンで分析可能なインターフェース（`OpenDataHub`）に統合するツールキットです。
需要予測（Darts）やビジネス分析において、「外部要因（市況、天候、トレンド）」をモデルに供給するための**データパイプラインの心臓部**として機能します。

---

## 🧠 Progressive Disclosure (When to use what)
推論スピードを最大化するため、取得可能なデータの詳細一覧や具体的なCLIコマンドは外部ファイルに分離（プログレッシブ開示）されています。**絶対にコマンドやデータ構造を推測しないでください。**

- **どんなデータ（経済、天候、トレンド等）が取得可能か、またその詳細を知りたい場合**は、必ず以下を読んでください。
  - `read_file("references/capabilities.md")`
- **スクリプトの実行方法、`OpenDataHub` の使い方、CLI引数を知りたい場合**は、必ず以下を読んでください。
  - `read_file("references/usage_guide.md")`
- **システム要件、機能一覧、非機能要件、制約条件を正確に知りたい場合**は、以下を読んでください。
  - `read_file("docs/REQUIREMENTS.md")`
- **各データソースの利用規約・出典表記・商用利用の制約を知りたい場合**は、以下を読んでください。
  - `read_file("docs/DATA_SOURCE_TERMS.md")`

---

## 🛠️ コア・アーキテクチャ (Core Principles)

- **Polars First**: パフォーマンスとメモリ効率のため、内部データ処理の標準は `pandas` ではなく `polars` を採用しています。
- **Unified Interface**: 各データソースの個別スクリプトに加え、全てを統括する `scripts/opendata_hub.py` を提供し、呼び出し元の複雑性を隠蔽します。
- **Resilience**: 一時的エラー（HTTP 429/5xx・接続・タイムアウト）のみをリトライし、プログラムエラーは即送出するリトライ層を標準装備しています。
- **Fail Loud, Not Silent**: 取得失敗（パース失敗等）を「データ無し」と誤認させず、欠損covariateの混入を防ぎます。退化データ（空・全null）はキャッシュしません。
- **Return-value First**: フェッチャーの戻り値DataFrameを優先消費し、CSV経由の型喪失（日付の文字列化）を回避します（`_fetch_to_df`）。
- **Parallel & Align**: `OpenDataHub.get_many()` で多ソースを並列取得し、`scripts/time_align.py` で異周波数の外生変数を共通周波数に揃えてからモデルに供給できます。

---

## 📜 License & Data Terms

本ソフトウェアは MIT License です（`LICENSE` 参照）。取得したデータの利用条件は各提供元の規約に従います — `docs/DATA_SOURCE_TERMS.md` を参照してください。