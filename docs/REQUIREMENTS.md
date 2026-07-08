# 要件定義書

**システム名**: opendata-skill
**バージョン**: 2.2.0 (Robustness & JP Leading Indicators)
**作成日**: 2026-04-18（最終更新: 2026-06-27）
**対象リポジトリ**: `opendata-skill`（単独リポジトリ）

---

## 目次

1. [目的・スコープ](#1-目的スコープ)
2. [システム概要](#2-システム概要)
3. [機能要件](#3-機能要件)
4. [データソース仕様](#4-データソース仕様)
5. [入出力仕様](#5-入出力仕様)
6. [非機能要件](#6-非機能要件)
7. [外部依存サービス](#7-外部依存サービス)
8. [CLIインターフェース仕様](#8-cliインターフェース仕様)
9. [環境変数仕様](#9-環境変数仕様)
10. [制約・前提条件](#10-制約前提条件)
11. [品質保証](#11-品質保証)
12. [用語集](#12-用語集)

---

## 1. 目的・スコープ

### 1.1 目的

世の中に散在するオープンデータ API・外部統計サービスを、単一のクリーンな Python インターフェース（`OpenDataHub`）に統合し、SCM 需要予測・マーケティング分析・経済分析に必要な「外部要因（市況・天候・トレンド・地政学リスク）」を一元的に取得可能とするツールキットを提供する。

### 1.2 スコープ（対象）

- 44種類のオープンデータ API / 公開統計サービスへのアクセス
- Polars ネイティブ処理による高速データ取得・変換
- キャッシュ機構による API レートリミット回避
- CSV 出力と DataFrame 返却の両対応
- 産業別コモディティ価格プロキシの自動取得（18産業）
- グローバルマクロ指標プリセット（米・中・欧・日）
- SCM 先行指標（PMI・UN Comtrade・EIA・GDELT・日銀短観・景気動向指数）
- 地政学リスク・自然災害リスクデータ（USGS・NASA FIRMS・ACLED代替）
- 複数ソースの並列取得（`get_many`）と異周波数 covariate の周波数アラインメント（`time_align`）

### 1.3 スコープ外

- 取得データの予測モデル化（別スキル `darts-forecast-skill` の責務）
- データ可視化・ダッシュボード生成（呼び出し側の責務）
- リアルタイムストリーミング（バッチ取得のみ）
- ユーザー認証・権限管理
- 取得データの長期蓄積・データウェアハウス機能（`BigQuery` スキルの責務）

---

## 2. システム概要

### 2.1 処理フロー

```
呼び出し元 (darts-forecast-skill, consultant-toolkit, etc.)
  ↓
OpenDataHub.get_xxx()
  ↓
CacheManager 確認 (ヒット → 返却)
  ↓ (ミス時)
_fetch_to_df(): _load_module() で個別フェッチャーを動的ロード
  ↓
{source}_fetcher.fetch_xxx_data() で API 呼び出し
  ↓ (リトライ・レートリミット適用)
戻り値が DataFrame → 直接消費（型を保持）
戻り値が None     → ユニーク名 temp CSV へフォールバック
  ↓
_normalize_df() でカラム名標準化 (date / value)
  ↓
_is_degenerate() でない場合のみ CacheManager.set() で保存
  ↓
Polars DataFrame 返却（オプションで CSV 出力）
```

### 2.2 アーキテクチャ

3層構造の責務分離を採用する。

```
┌─────────────────────────────────────────────┐
│ OpenDataHub (scripts/opendata_hub.py)       │  統合IF層
│  ├─ get_weather / get_economic / get_yahoo  │  （キャッシュ・動的ロード）
│  ├─ get_pmi / get_comtrade / get_boj_tankan │
│  ├─ get_many (並列ファンアウト)             │
│  └─ _fetch_to_df / _normalize_df /          │
│     _is_degenerate / _cached_fetch          │
└─────────────────────────────────────────────┘
             ↓ 動的 import
┌─────────────────────────────────────────────┐
│ 個別フェッチャー (39 本)                    │  データ取得層
│  ├─ *_fetcher.py                            │  （CLI + 関数API）
│  └─ fetch_xxx_data()                        │
└─────────────────────────────────────────────┘
             ↓ 共通ユーティリティ
┌─────────────────────────────────────────────┐
│ api_utils / cache_manager / time_align      │  インフラ層
│  ├─ require_api_key / rate_limited          │
│  ├─ retry_with_ratelimit (429/5xxのみ)      │
│  ├─ CacheManager (TTL付き)                  │
│  └─ align_frequency / align_many            │
└─────────────────────────────────────────────┘
```

### 2.3 設計原則

| 原則 | 説明 |
|---|---|
| **Polars First** | 内部データ処理は Polars で統一。pandas は yfinance / wbgapi 依存部のみ |
| **Unified Interface** | `OpenDataHub` が全データソースへの単一入口。個別スクリプトも独立利用可能 |
| **Progressive Disclosure** | `SKILL.md` をエントリとし、詳細は `references/` に委譲して推論効率を最大化 |
| **Resilience** | `tenacity` によるリトライ、レートリミッター、親切な APIキー不在メッセージ |
| **Cache-First** | CacheManager による TTL 付きローカルキャッシュで API 負荷を軽減 |

---

## 3. 機能要件

### 3.1 統合ハブ (`OpenDataHub`)

| 機能ID | 機能 | 概要 |
|---|---|---|
| F-HUB-01 | フェッチャー自動検出 | `scripts/*_fetcher.py` を glob で検出し、動的にロード可能 |
| F-HUB-02 | キャッシュ付き取得 | `_cached_fetch()` 共通ヘルパーで、全データソースに対し TTL 付きキャッシュを適用 |
| F-HUB-03 | カラム名標準化 | `_normalize_df()` が `date`, `value` 系カラムを統一命名に変換（戻り値経由・CSV経由の両方に適用、衝突安全・冪等） |
| F-HUB-04 | 産業別プリセット | `INDUSTRY_COMMODITY_MAP` により18産業に関連するコモディティ価格を一括取得 |
| F-HUB-05 | グローバルマクロプリセット | 米・中・欧・日の主要マクロ指標をワンクリックで取得 |
| F-HUB-06 | 戻り値DF優先消費 | `_fetch_to_df()` がフェッチャーの戻り値 DataFrame を優先消費し、`None` 返しのみ temp CSV へフォールバック（CSV経由の型喪失＝日付の文字列化を回避）。temp名はユニーク化し並列実行時の競合を防ぐ |
| F-HUB-07 | 非退化検証 | `_is_degenerate()`（空 / 全カラム全null）でない場合のみキャッシュ保存。誤データの固着を防止 |
| F-HUB-08 | 並列ファンアウト | `get_many()` が複数ソースをスレッドプールで並列取得。個々の失敗は隔離し、その label は空DFを返す |

### 3.2 データ取得機能

#### 3.2.1 経済・金融（コア）

| 機能ID | データソース | スクリプト | 取得内容 |
|---|---|---|---|
| F-ECON-01 | Yahoo Finance | `yahoo_fetcher.py` | 株価・為替・コモディティ先物 OHLCV |
| F-ECON-02 | World Bank | `worldbank_fetcher.py` | GDP・人口・インフレ率（エイリアス対応） |
| F-ECON-03 | OECD | `oecd_fetcher.py` | MEI・QNA・労働市場統計 |
| F-ECON-04 | e-Stat | `estat_fetcher.py` | 日本政府統計（国勢調査・CPI・機械受注） |
| F-ECON-05 | FRED | `fred_fetcher.py` | 米マクロ経済指標（UNRATE・CPIAUCSL等） |
| F-ECON-06 | Freight | `freight_fetcher.py` | BDI・物流関連 ETF |

#### 3.2.2 先行指標・SC リスク（v2.1 新規）

| 機能ID | データソース | スクリプト | 取得内容 |
|---|---|---|---|
| F-LEAD-01 | PMI / OECD CLI | `pmi_fetcher.py` | 製造業新規受注・景気先行指数・政策不確実性指数 |
| F-LEAD-02 | UN Comtrade | `comtrade_fetcher.py` | HSコード粒度のグローバル貿易フロー |
| F-LEAD-03 | EIA | `eia_fetcher.py` | 米原油/ガス在庫・精製所稼働率 |
| F-LEAD-04 | GDELT | `gdelt_fetcher.py` | 地政学イベント・SC断絶の時系列／記事／感情分析 |
| F-LEAD-05 | AIS / 港湾混雑 | `ais_fetcher.py` | 主要15港湾の船舶AIS位置・混雑度 |
| F-LEAD-06 | 日銀 短観 TANKAN | `boj_fetcher.py` | 業況判断DI（大企業/中堅/中小・製造業/全産業、最近・先行き）。BOJ時系列API・キー不要 |
| F-LEAD-07 | 内閣府 景気動向指数 | e-Stat `0003446461`（`get_keiki_di`） | CI/DI 先行指数・一致指数・遅行指数 |
| F-LEAD-08 | JNTO 訪日外客数 | e-Stat `0003449064`（`get_inbound_visitors`） | 港別 入国外国人の国籍・地域別人数（月次） |

#### 3.2.3 環境・インフラ

| 機能ID | データソース | スクリプト | 取得内容 |
|---|---|---|---|
| F-ENV-01 | Open-Meteo | `meteo_fetcher.py` | 気温・降水量・風速（1時間/日次） |
| F-ENV-02 | Air Quality | `air_quality_fetcher.py` | PM2.5・NO2・オゾン濃度 |
| F-ENV-03 | TEPCO | `power_fetcher.py` | 東京電力管内の電力使用状況 |
| F-ENV-04 | ENTSO-E | `entsoe_fetcher.py` | 欧州15カ国の電力需給・価格 |

#### 3.2.4 地域・都市

| 機能ID | データソース | スクリプト | 取得内容 |
|---|---|---|---|
| F-REG-01 | MLIT | `mlit_fetcher.py` | 不動産取引価格・地価公示 |
| F-REG-02 | RESAS | `resas_fetcher.py` | 地域経済分析（人口動態・産業構造） |
| F-REG-03 | PLATEAU | `plateau_fetcher.py` | 3D都市モデルメタデータ |
| F-REG-04 | ODPT | `odpt_fetcher.py` | 公共交通オープンデータ |

#### 3.2.5 業界特化

| 機能ID | データソース | スクリプト | 取得内容 |
|---|---|---|---|
| F-IND-01 | USDA / FAOSTAT | `usda_fetcher.py` | 米国/グローバル農業統計・食料需給バランス |
| F-IND-02 | 半導体 (FRED経由) | `semicon_fetcher.py` | 出荷・在庫・Book-to-Bill 比 |

#### 3.2.6 グローバルリスク・補完（v2.1 新規）

| 機能ID | データソース | スクリプト | 取得内容 |
|---|---|---|---|
| F-RISK-01 | USGS | `usgs_fetcher.py` | グローバル地震リアルタイム |
| F-RISK-02 | NASA FIRMS | `firms_fetcher.py` | 山火事衛星観測ホットスポット |
| F-RISK-03 | J-SHIS | `jshis_fetcher.py` | 日本の地震確率論的評価 |
| F-RISK-04 | River Info | `river_fetcher.py` | 河川水位（洪水リスク） |

#### 3.2.7 公的為替（v2.1 新規）

| 機能ID | データソース | スクリプト | 取得内容 |
|---|---|---|---|
| F-FX-01 | ECB | `official_fx_fetcher.py` | EU 公式参照為替レート (SDMX経由) |
| F-FX-02 | Frankfurter/JPY | `official_fx_fetcher.py` | ECB派生の円建てクロスレート（会計参照用） |

#### 3.2.8 トレンド・ソーシャル

| 機能ID | データソース | スクリプト | 取得内容 |
|---|---|---|---|
| F-SOC-01 | Google Trends | `trends_fetcher.py` | 検索キーワード関心度（0-100） |
| F-SOC-02 | YouTube | `youtube_fetcher.py` | 動画コメント・エンゲージメント |
| F-SOC-03 | xAI Grok | `x_grok_fetcher.py` | X (Twitter) リアルタイム投稿 |
| F-SOC-04 | Events | `events_fetcher.py` | 祝日・地域イベント |

#### 3.2.9 ユーティリティ

| 機能ID | データソース | スクリプト | 取得内容 |
|---|---|---|---|
| F-UTIL-01 | ZipCloud | `zipcode_fetcher.py` | 郵便番号→住所変換 |
| F-UTIL-02 | GSI Maps | `gsi_fetcher.py` | 住所→緯度経度ジオコーディング |
| F-UTIL-03 | National Tax | `corp_fetcher.py` | 法人番号・企業情報 |
| F-UTIL-04 | Feature Engineer | `feature_engineer.py` | ラグ変数・移動平均・カレンダーフラグ生成 |

### 3.3 分析支援機能

| 機能ID | 機能 | 概要 |
|---|---|---|
| F-ANA-01 | 相関分析 | `correlation_analyzer.py` で2つのデータセット間の相関を Pearson/Spearman で算出 |
| F-ANA-02 | データサジェスター | `data_suggester.py` が `INDUSTRY_GUIDE.md` をキーワード検索し、目的に適したデータソースを提案（静的マッピング表ベース。LLM呼び出しなし） |
| F-ANA-03 | Book-to-Bill計算 | `semicon_fetcher.compute_book_to_bill()` で半導体業界のB2B比を自動計算（出荷0/null時は inf を出さず null） |
| F-ANA-04 | 周波数アラインメント | `time_align.py` の `align_frequency`（単一系列を目標周波数へresample）/ `align_many`（複数ソースを共通グリッドで横結合）。`filter_col` で多次元e-Statを1系列に絞って合成可能 |
| F-ANA-05 | 特徴量生成 | `feature_engineer.py` でラグ・移動平均・カレンダーフラグ・欠損補完。日付parseは複数フォーマット試行、解析不能時は raise（黙ってnull化しない） |

---

## 4. データソース仕様

### 4.1 APIキー要否マトリクス

| 分類 | データソース | APIキー | 無料枠 |
|---|---|---|---|
| **不要** | GDELT, USGS, FAOSTAT, ECB, Frankfurter, Open-Meteo, ODPT, ZipCloud, PLATEAU, 祝日, GSI | なし | 無制限 |
| **要登録・無料** | FRED, EIA, ENTSO-E, NASA FIRMS, USDA QuickStats, e-Stat, RESAS, MLIT, 国税庁 | `*_API_KEY` | 制限あり |
| **要登録・有料** | xAI Grok, YouTube Data API | `*_API_KEY` | 制限あり |
| **要契約** | UN Comtrade Premium, Datalastic AIS | `*_API_KEY` | 有料 |

### 4.2 レートリミット

| データソース | 制限 | 対応 |
|---|---|---|
| e-Stat | `@rate_limited(max_calls=2, period=1.0)` = 2req/秒に自制 | `rate_limited` デコレータで自動待機 |
| OECD | 同一時間に過剰リクエスト禁止 | `@rate_limited(1req/秒)` + 一時的エラーは送出して `retry_with_ratelimit` で再試行 |
| GDELT | 明記なしだが秒間数リクエスト推奨 | 60秒タイムアウト |
| UN Comtrade Public | 500レコード/クエリ、100クエリ/時 | ユーザー側で period を絞る責務 |

### 4.3 キャッシュTTL

| データ種別 | TTL | 根拠 |
|---|---|---|
| USGS地震・FIRMS山火事 | 1-3時間 | リアルタイム性重視 |
| AIS港湾混雑 | 2時間 | 船舶位置は日次で大きく変動 |
| GDELT・ENTSO-E | 6時間 | 時間単位のイベント・電力需給 |
| 株価・天候 | 12-24時間 | 日次更新 |
| PMI・公的為替・EIA・日銀短観 | 24-168時間 | 週次/月次/四半期更新 |
| 国勢調査・農業統計・景気動向指数・訪日外客数 | 720時間 (30日) | 月次/年次更新 |

---

## 5. 入出力仕様

### 5.1 入力

| 項目 | 形式 | 説明 |
|---|---|---|
| データソース指定 | エイリアス文字列 or API固有コード | 例: `"gdp"` → `NY.GDP.MKTP.CD` |
| 期間 | `YYYY-MM-DD` または `YYYYMMDD` | ソースごとに仕様差あり |
| 地域 | ISO2 / ISO3 / M49 コード | `COUNTRY_M49` 等で自動変換 |
| APIキー | `.env` ファイル経由 | `api_utils.require_api_key()` が読み込み |

### 5.2 出力

#### 5.2.1 関数API（推奨）

```python
from scripts.opendata_hub import OpenDataHub
hub = OpenDataHub()
df: polars.DataFrame = hub.get_xxx(...)
```

**標準カラム**:
| カラム名 | 型 | 説明 |
|---|---|---|
| `date` | Utf8 / Date | 日付（`YYYY-MM-DD` または ISO8601 文字列） |
| `value` | Float64 | 数値（欠損は null） |
| `series` / `pair` / `country` | Utf8 | メタ情報（データソースごとに異なる） |

#### 5.2.2 CLI

```bash
uv run python scripts/{source}_fetcher.py --xxx --out output.csv
```

- 終了コード: 0（成功）/ 1（APIキー不足）/ その他（ネットワークエラー等）
- 出力 CSV: UTF-8 BOM 無し、`date,value,...` ヘッダ

### 5.3 エラーハンドリング

| エラー種別 | 動作 |
|---|---|
| APIキー未設定 | 親切なメッセージ（取得URL含む）を stderr に出力 → `sys.exit(1)` |
| HTTP 4xx (429以外) | 非一時的エラー。リトライせず即送出（無駄なバックオフを避ける） |
| HTTP 429 / 5xx | 一時的エラー。`tenacity` で最大5回リトライ（Exponential Backoff 2→10秒） |
| 接続エラー・タイムアウト | 一時的エラー。同上のリトライ対象 |
| プログラムエラー (KeyError等) | 非一時的。リトライせず即送出（バグを隠さない） |
| CSVパース失敗（ファイルは存在） | **空DFに化けさせず例外を送出**。取得失敗を「データ無し」と誤認させない（v2.2で変更） |
| 取得結果が空 / 全null | 退化データとしてキャッシュせず、空DFを返す（正当な「データ無し」） |

---

## 6. 非機能要件

### 6.1 性能

| 項目 | 目標値 |
|---|---|
| キャッシュヒット時の応答時間 | < 100ms |
| API呼び出し時の応答時間 | < 30秒（タイムアウト） |
| 一括フェッチ（`examples/all_concurrent_tester.py`） | < 5分（全ソース） |

### 6.2 信頼性

- 一時的障害（429/5xx・接続・タイムアウト）は `tenacity` で自動リトライし耐性を持つ。多くの個別フェッチャーは最終的に空 DataFrame を返してパイプラインを止めない
- ただし「取得失敗」を「データ無し（空DF）」と無差別に同一視しない: CSVパース失敗やプログラムエラーは黙って空DFに化けさせず送出し、欠損covariate の混入を防ぐ（v2.2の方針転換）
- 退化データ（空・全null）はキャッシュせず、誤データの固着を防ぐ
- API キー不在時は実行時に早期失敗（lazy evaluation ではなく eager check）
- `get_many` の並列実行では1ソースの失敗を隔離し、他ソースを巻き込まない

### 6.3 保守性

- 各フェッチャーは単一ファイル、100-250行程度に制限
- CLI と関数APIの両対応（`fetch_xxx_data()` + `main()`）
- 新規ソース追加時: `scripts/{name}_fetcher.py` を追加するだけで `OpenDataHub` が自動検出
- `_cached_fetch()` ヘルパーにより Hub のメソッド追加が3-6行で済む

### 6.4 互換性

- Python 3.12以上
- OS: Windows 11 / macOS / Linux
- 主要依存: `polars`, `requests`, `tenacity`, `python-dotenv`, `yfinance`, `wbgapi`

---

## 7. 外部依存サービス

### 7.1 必須ライブラリ

```toml
[project.dependencies]
polars                   # データ処理の中核
requests                 # HTTP クライアント
tenacity                 # リトライロジック
python-dotenv            # .env 読み込み（多数のフェッチャーが runtime import）
yfinance                 # Yahoo Finance (pandas依存)
wbgapi                   # World Bank
pandas                   # yfinance/wbgapi互換のため
pytrends                 # Google Trends
edinetdb                 # EDINET 財務データ
matplotlib               # correlation_analyzer の可視化
seaborn                  # correlation_analyzer の可視化
google-api-python-client # youtube_fetcher
openmeteo-requests       # ※現状コードでは未使用（将来用）
requests-cache           # ※現状コードでは未使用（将来用）
retry-requests           # ※現状コードでは未使用（将来用）
jpholiday                # ※現状コードでは未使用（将来用）
```

### 7.2 テスト用依存

```toml
[dependency-groups.dev]
pytest           # テストランナー
```
（`python-dotenv` は runtime import されるため v2.2 で `[project.dependencies]` へ移動。dev-group only だと `pip install .` 系で `ModuleNotFoundError: dotenv` になっていた）

### 7.3 外部API（SLA非保証）

本スキルは以下の第三者 API に依存しており、それらの可用性・レスポンス構造変更のリスクを負う。重要な業務利用には実API smoke test の定期実行を推奨する。

- 政府機関: e-Stat, MLIT, RESAS, USGS, EIA, USDA, BOJ, ECB
- 民間: Yahoo Finance, Google Trends, YouTube, xAI Grok, Datalastic
- 国際機関: UN Comtrade, World Bank, OECD, FAOSTAT, ENTSO-E
- NGO/研究: GDELT, NASA FIRMS, Open-Meteo

---

## 8. CLIインターフェース仕様

### 8.1 共通CLIパターン

全フェッチャーが以下のパターンを踏襲する:

```bash
uv run python scripts/{source}_fetcher.py \
    --{source-specific-args} \
    --start YYYY-MM-DD \
    --end YYYY-MM-DD \
    --out output.csv
```

### 8.2 代表例

```bash
# Yahoo Finance (トヨタ + ドル円)
uv run python scripts/yahoo_fetcher.py --tickers 7203.T USDJPY=X --start 2023-01-01

# PMI (米国製造業新規受注)
uv run python scripts/pmi_fetcher.py --series us_new_orders --start 2020-01-01

# UN Comtrade (日中半導体貿易)
uv run python scripts/comtrade_fetcher.py --reporter JP --partner CN --hs 8542

# GDELT (SC断絶イベント)
uv run python scripts/gdelt_fetcher.py --query "port congestion" --theme port_congestion

# USGS 地震
uv run python scripts/usgs_fetcher.py --min-mag 5.0

# ENTSO-E 欧州電力
uv run python scripts/entsoe_fetcher.py --type day_ahead_price --country DE
```

---

## 9. 環境変数仕様

### 9.1 APIキー環境変数一覧

`.env` ファイルをプロジェクトルートに配置する。

```env
# ── v1.x (既存) ─────────────────────────
ESTAT_API_KEY=<e-Stat App ID>
RESAS_API_KEY=<RESAS API Key>
MLIT_API_KEY=<MLIT API Key>
FRED_API_KEY=<FRED API Key>
XAI_API_KEY=<xAI Grok API Key>
GOOGLE_API_KEY=<Gemini API Key>
YOUTUBE_API_KEY=<YouTube Data API Key>
CORP_API_KEY=<gBizINFO / 法人番号システム API Key>
ODPT_API_KEY=<ODPT 公共交通オープンデータ API Key>

# ── v2.2 (新規・キー不要) ────────────────
# 日銀短観 (boj_fetcher) / 景気動向指数・訪日外客数 (e-Stat経由) は
# 追加キー不要 (短観はキー不要、e-Stat系は ESTAT_API_KEY を流用)

# ── v2.1 (新規) ─────────────────────────
EIA_API_KEY=<EIA API Key>
ENTSOE_API_KEY=<ENTSO-E API Key>
USDA_API_KEY=<USDA NASS API Key>
NASA_FIRMS_API_KEY=<NASA FIRMS MAP Key>
COMTRADE_API_KEY=<UN Comtrade Premium Key>  # optional
DATALASTIC_API_KEY=<Datalastic AIS Key>     # optional
AISHUB_USERNAME=<AISHub username>           # optional
```

### 9.2 APIキー取得元 URL

| 環境変数 | 取得元 |
|---|---|
| `FRED_API_KEY` | https://fred.stlouisfed.org/docs/api/api_key.html |
| `ESTAT_API_KEY` | https://www.e-stat.go.jp/api/ |
| `EIA_API_KEY` | https://www.eia.gov/opendata/register.php |
| `ENTSOE_API_KEY` | https://transparency.entsoe.eu/ |
| `USDA_API_KEY` | https://quickstats.nass.usda.gov/api |
| `NASA_FIRMS_API_KEY` | https://firms.modaps.eosdis.nasa.gov/api/map_key/ |
| `DATALASTIC_API_KEY` | https://datalastic.com |

---

## 10. 制約・前提条件

### 10.1 前提条件

- プロジェクトルートに `.env` ファイルが存在すること（または環境変数が設定されていること）
- Python 3.12 以上
- インターネット接続（初回取得時）
- キャッシュディレクトリへの書き込み権限（デフォルト: `.cache/`）

### 10.2 制約

| 項目 | 制約内容 |
|---|---|
| BOJ 公式為替 | 公的為替の `fetch_jpy_fx` は Frankfurter (ECB派生) を代替使用。なお BOJ 時系列統計データ検索 API はキー不要で利用でき、`boj_fetcher.py` が短観などをこの API から取得している（為替系列も同 API で取得可能） |
| 景気動向指数 / 訪日外客数 | `get_keiki_di` / `get_inbound_visitors` は e-Stat の多次元テーブル（date×系列、港×国籍）を生で返す。`time_align.align_frequency(filter_col=..., filter_val=...)` で1系列に絞らないと、周波数アライン時に系列が平均され混ざる |
| WSTS/SEMI B2B | 本家 WSTS/SEMI の Book-to-Bill は会員制のため、`semicon_fetcher` は FRED 公開代替系列から算出 |
| ISM PMI | ISM 本体のライセンス制約により、`pmi_fetcher` は FRED 公開の関連指標（新規受注・OECD CLI等）で代替 |
| UN Comtrade | 無料 API は 500レコード/クエリの制限。大量データ取得には有料キー必須 |
| Datalastic AIS | 有料 API。無料代替は AISHub (登録制) |

### 10.3 非対応事項

- データソースの SLA は第三者依存。本スキルは無保証
- 取得データの正確性は発行元の責任。本スキルはパイプライン提供のみ
- 破壊的変更時は `BACKLOG.md` に記載し、`SKILL.md` バージョンをインクリメント

---

## 11. 品質保証

### 11.1 テスト戦略

| テスト種別 | 対象 | 方式 |
|---|---|---|
| **実APIテスト (キー不要)** | GDELT, USGS, ECB, Frankfurter, FAOSTAT | 実際にHTTP呼び出し |
| **実APIテスト (キー設定済)** | PMI, Semicon (FRED経由) | 実際にFRED呼び出し |
| **モックテスト** | Comtrade, EIA, AIS, ENTSO-E, FIRMS, USDA QS | `unittest.mock.patch` でHTTPレスポンス注入 |

### 11.2 テストカバレッジ

- v2.1 までのフェッチャー: 111 テスト
- v2.2 追加（バグ回帰 + Hub堅牢化/戻り値経路/並列/time_align/BOJ/JPプリセット）: 約55 テスト
- 合計: **166 passed / 1 skipped (FAOSTAT 外部API一時障害)**

### 11.3 CI/CD 想定

```bash
uv run pytest tests/
```

- 大半はモックテスト（`test_trends.py` 含め `unittest.mock` で HTTP を注入）でネットワーク不要
- 一部の実APIテスト（FAOSTAT等）はネットワーク必須。外部API一時障害時は `@pytest.mark.skipif` 等でスキップ
- `FRED_API_KEY` 無設定環境では該当する実APIテストがスキップ

### 11.4 コード品質

- Ruff 準拠 (`DTZ005` / `BLE001` 等を原則無違反)
- `datetime.now(timezone.utc)` 強制 (GEMINI.md 憲法遵守)
- 型ヒント必須

---

## 12. 用語集

| 用語 | 説明 |
|---|---|
| **SCM** | Supply Chain Management (サプライチェーンマネジメント) |
| **S&OP** | Sales & Operations Planning (販売・業務計画) |
| **PMI** | Purchasing Managers' Index (購買担当者景気指数) |
| **ISM** | Institute for Supply Management (米 供給管理協会) |
| **CLI (OECD)** | Composite Leading Indicator (景気先行指数) |
| **HS コード** | Harmonized System (国際商品統一分類) |
| **M49** | UN Statistical Division の国コード標準 |
| **AIS** | Automatic Identification System (船舶自動識別装置) |
| **BDI** | Baltic Dry Index (バルチック海運指数) |
| **WSTS** | World Semiconductor Trade Statistics |
| **SEMI** | Semiconductor Equipment and Materials International |
| **Book-to-Bill** | 新規受注 ÷ 出荷額。1.0超は業界拡張期 |
| **ENTSO-E** | European Network of Transmission System Operators for Electricity |
| **EIA** | U.S. Energy Information Administration |
| **GDELT** | Global Database of Events, Language, and Tone |
| **USGS** | United States Geological Survey |
| **FIRMS** | Fire Information for Resource Management System (NASA) |
| **SDMX** | Statistical Data and Metadata eXchange |
| **TTL** | Time To Live (キャッシュ有効期間) |
| **Progressive Disclosure** | エントリー文書を簡潔に保ち、詳細は参照ファイルに委譲する設計手法 |
| **短観 / TANKAN** | 日銀「全国企業短期経済観測調査」。業況判断DIが代表指標 |
| **業況判断DI** | 「良い」回答比率 −「悪い」回答比率。企業景況感の Diffusion Index |
| **景気動向指数 (CI/DI)** | 内閣府。CI=変化の大きさ、DI=変化方向の波及度。先行/一致/遅行の3系列 |
| **訪日外客数** | 日本を訪れた外国人旅行者数。インバウンド需要の指標 |

---

**改訂履歴**

| 版 | 日付 | 変更内容 |
|---|---|---|
| 1.0.0 | 2025-XX-XX | 初版（e-Stat / Yahoo / World Bank / Open-Meteo 中心） |
| 2.0.0 | 2026-04-14 | Agentic Evolution: APIキー自動検証・レートリミッター・グローバルマクロプリセット・特徴量自動補完 |
| 2.1.0 | 2026-04-18 | SCM Leading Indicators Expansion: PMI/Comtrade/EIA/GDELT/AIS/USDA/Semicon/ENTSO-E/USGS/FIRMS/ECB 11本新規、リファクタリング（`_cached_fetch`ヘルパー抽出・FRED統合・DTZ005遵守・entsoe重複キー修正・BOJ命名修正） |
| 2.2.0 | 2026-06-27 | **バグ監査38件修正**（corp XML/comtrade World=0/ais経度/eia facet/jshis震度/feature_engineer日付/odptネスト/worldbank部分期間/semicon ゼロ除算/retry述語を429・5xxのみに/entsoe processType/oecd retry有効化/estat重複列/gdelt空timeline/429リトライ/パッケージング欠落 ほか）。**機能追加**: 戻り値DF優先消費（temp CSVラウンドトリップ廃止）・非退化検証・`get_many`並列ファンアウト・`time_align`周波数アライン・日銀短観/景気動向指数/訪日外客数の3先行指標。166 passed/1 skip |
