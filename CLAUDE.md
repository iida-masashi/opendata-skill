# CLAUDE.md

このファイルは、このリポジトリで作業する Claude Code (claude.ai/code) に向けたガイダンスです。

## これは何か

`opendata-skill` は、約44のオープンデータ・外部API（e-Stat、日銀短観、RESAS、不動産情報ライブラリ、PLATEAU、FRED、World Bank、OECD、UN Comtrade、EIA、ENTSO-E、NASA FIRMS、GDELT、AIS港湾混雑、Open-Meteo、Google Trends、Yahoo Finance 等）を単一インターフェース `OpenDataHub`（`scripts/opendata_hub.py`）に統合するデータ取得ツールキットです（単独利用・AIエージェント向けスキルの両方として利用可能）。`darts-forecast-skill` のような需要予測・分析ツールに外生変数（マクロ経済・天候・トレンド・地政学リスク）を供給するために存在します。

Progressive disclosure（段階的開示）: `SKILL.md` がAIエージェント向けのエントリポイントで、詳細情報は明示的に `references/capabilities.md`（取得可能データの全カタログ）、`references/usage_guide.md`（CLI/API使用法）、`docs/REQUIREMENTS.md`、`docs/DATA_SOURCE_TERMS.md` に委譲しています。データソースを追加する場合や「何が取得できるか」に答える場合は、フェッチャー名から推測せずこれらのファイルを読んでください。

## コマンド

```bash
uv sync                        # 依存関係インストール（Python >=3.12 必須）
cp env.example .env            # 必要なキーだけ設定。ほとんどのソースはキー不要

uv run pytest tests/                        # 全テスト実行
uv run pytest tests/test_eia.py             # 単一テストファイル
uv run pytest tests/test_eia.py::test_mock_crude_stocks -v   # 単一テスト

uv run python scripts/yahoo_fetcher.py --tickers 7203.T USDJPY=X --start 2023-01-01
uv run python scripts/meteo_fetcher.py --lat 35.6895 --lon 139.6917 --historical
```

すべての `*_fetcher.py` は `argparse`（`if __name__ == "__main__"`）により単独実行可能で、かつ Hub 経由でインポート・呼び出しも可能です。APIキーが必要なソースのテストは、対応する環境変数が未設定の場合は自動スキップ（または `tests/test_eia.py` のようにモックキーにフォールバック）します — 実際の認証情報がないことを理由に修正を保留しないでください。

## アーキテクチャ

### OpenDataHub が唯一の統合ポイント

`scripts/opendata_hub.py` の `OpenDataHub` クラスは、初期化時に `scripts/*_fetcher.py` を全て自動検出し（`_discover_fetchers`、ファイル名サフィックスによる glob — **新しいフェッチャーはファイル命名規則だけで自動登録され、手動の登録作業は不要**）、`importlib` でモジュールをオンデマンドに動的ロードします。各 `get_*` メソッド（例: `get_weather`、`get_pmi`、`get_boj_tankan`）は共通の形をしています:

1. `params` dict を構築 → `CacheManager`（Parquetベース、TTLはソースの変動性により異なる: 天候/AIS/GDELTは数時間、為替/市場データは12〜24時間程度、マクロ/貿易データは1週間〜1ヶ月）を確認。
2. キャッシュミス時は `_fetch_to_df`（またはv2.1以降のソース向け共通ヘルパー `_cached_fetch`）を呼び、フェッチャーモジュールをロードして `fetch_*`/`compute_*` 関数を呼び出す。
3. 結果が「退化」（`_is_degenerate`: 空、または全カラムが全行null）していればキャッシュをスキップ — 取得失敗を正当な欠損データのようにキャッシュしてはならない。
4. 正規化された Polars DataFrame を返す（`_normalize_df` がソース固有のカラム名を `date`/`value` の契約にマッピング）。

新しいデータソースの追加は `scripts/<name>_fetcher.py` を配置し、Hub に `get_<name>` メソッドを配線する（一般的なケースでは `_cached_fetch` を再利用する）ことで行います — レジストリを編集するのではありません。

### 戻り値優先・CSVフォールバックの取得方式 (`_fetch_to_df`)

フェッチャーは DataFrame を直接返すか、CSV のみを書き出す（古いソース）かのどちらかです。`_fetch_to_df` は戻り値を優先し、CSVラウンドトリップによる型喪失（日付の文字列化など）を回避します。フェッチャーが `None` を返した場合のみ一時CSVを読みます。一時CSVのファイル名は（呼び出し側が固定名を渡していても）常に `uuid4` サフィックスでユニーク化されるため、`get_many` の並列実行時に複数のフェッチャーが共有CWD上の同じ一時ファイルを取り合う競合が起きません。

### Fail Loud, Not Silent（握り潰さない設計）

これは意図的で、設計上の中核原則です（`SKILL.md`、`BACKLOG.md` の v2.2 バグ監査ノート参照）— 取得失敗を「データ無し」と区別不能にしてはいけません。サイレントに空になった外生変数は下流の予測を汚染するためです:

- `api_utils.retry_with_ratelimit` は一時的エラー（ネットワークエラーおよびHTTP 429/5xx、`_is_transient` で判定）**のみ**を `tenacity` でリトライします。プログラムエラー（`KeyError`、`ValueError`、429以外の4xx）は即座に失敗し、無駄な5回リトライと指数バックオフを避けます。
- `OpenDataHub._csv_to_df`: 一時CSVが存在しない場合は「データ無し」（空DataFrame）を意味しますが、CSVは存在するのにパースに失敗した場合は例外を送出します — 空DataFrameへの縮退はしません。
- `CacheManager` / `_is_degenerate` は空または全null の結果を絶対にキャッシュしないため、一時的な失敗が「空」の古いキャッシュエントリ経由で以後の呼び出しを汚染することがありません。

フェッチャーや Hub の取得パスを触る際は、「取得失敗が確定した」と「取得に失敗した」の区別を維持してください。

### フェッチャーモジュールの規約

各 `scripts/<name>_fetcher.py` は典型的に以下を持ちます:

- `@retry_with_ratelimit` でデコレートされたリトライ付きヘルパー `_get_with_retry(url, **kwargs)`。**モジュールレベル**の `requests.get` を呼びます（共有クライアントではなく）— これはテストがモジュールごとに `@patch("<module>.requests.get")` できるようにするための意図的な設計です。
- `from api_utils import X` を `try/except ImportError: from .api_utils import X` で包む — スクリプト単独実行（`scripts/` が `sys.path` にある場合）と、Hub経由のパッケージ相対インポートの両方をサポートするため。
- 認証情報が必要なソース向けの `require_api_key(env_var, site_name, url)` 呼び出し（`api_utils.py` から）— わかりにくいエラーではなく、親切なセットアップ案内を表示して終了します。
- Polars DataFrame を返す `fetch_<name>_data(..., output_file: str | None = None) -> pl.DataFrame` 関数（これが推奨）。`output_file` が指定されればCSVも書き出します。
- `if __name__ == "__main__"` で保護された `argparse` ベースの `main()`。

一部のフェッチャー（例: `eia_fetcher.py`）は、共有REST エンドポイント上の名前付きプリセット用に `SERIES_ALIAS` / ファセットマッピング dict を公開します — エンドポイントがエイリアス間で共有される場合、区別用ファセットはエイリアスごとに明示的に設定する必要があります（過去のバグ: `crude_stocks`/`gasoline_stocks` がこれなしでは混在データをサイレントに返していました）。

### 時系列アラインメント (`scripts/time_align.py`)

`align_frequency` は単一の `date`/`value` 系列（Polars の `group_by_dynamic` 使用）を、設定可能な集約方法で目標周波数にリサンプリングします。`align_many` は複数ソースを共通の日付グリッドに結合し、予測モデルへの供給に使います。1日付あたり複数行を持つソース（例: e-Statの景気動向指数 = 系列 × 表章項目）は、アラインメントの前後で `filter_col`/`filter_val` により単一系列に絞り込む**必要があります**。そうしないと異なる系列の値がサイレントに混ざって集約されます。

### 並列ファンアウト (`Hub.get_many`)

複数の `get_*` 呼び出しを `ThreadPoolExecutor`（I/Oバウンドのため）で並列実行します。各specの失敗は隔離され、あるソースの例外はバッチ全体を失敗させるのではなく、そのラベルの空DataFrameになります。

## 重要な制約

- Python >=3.12、依存関係・パッケージ管理は `uv` 経由（pip/poetry直接ではない）。
- 内部標準のDataFrameライブラリは pandas ではなく Polars — pandasは相互運用の境界としてのみ登場します（例: `yfinance` は pandas を返し、`_coerce_to_polars` が Polars に変換）。
- 取得したデータの利用条件はソースごとに異なり、本リポジトリの MIT ライセンスの対象**外**です — 出典表記の必須要件、e-Stat/FRED/Open-Meteo の必須表記、商用利用制限に関わる変更を行う前に `docs/DATA_SOURCE_TERMS.md` を確認してください（Open-Meteo の無償枠は非商用限定、`yfinance`/`pytrends` は非公式・グレーゾーンなライブラリ、ODPT は開発者登録が必須）。
