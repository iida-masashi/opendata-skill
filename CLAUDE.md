# CLAUDE.md

このファイルは、このリポジトリで作業する Claude Code (claude.ai/code) に向けたガイダンスです。

## これは何か

`opendata-skill` は、約43のオープンデータ・外部API（e-Stat、日銀短観、不動産情報ライブラリ、PLATEAU、FRED、World Bank、OECD、UN Comtrade、EIA、ENTSO-E、NASA FIRMS、GDELT、AIS港湾混雑、Open-Meteo、Google Trends、Yahoo Finance 等）を単一インターフェース `OpenDataHub`（`scripts/opendata_hub.py`）に統合するデータ取得ツールキットです（単独利用・AIエージェント向けスキルの両方として利用可能）。`darts-forecast-skill` のような需要予測・分析ツールに外生変数（マクロ経済・天候・トレンド・地政学リスク）を供給するために存在します。

Progressive disclosure（段階的開示）: `SKILL.md` がAIエージェント向けのエントリポイントで、詳細情報は明示的に `references/capabilities.md`（取得可能データの全カタログ）、`references/usage_guide.md`（CLI/API使用法）、`docs/REQUIREMENTS.md`、`docs/DATA_SOURCE_TERMS.md` に委譲しています。データソースを追加する場合や「何が取得できるか」に答える場合は、フェッチャー名から推測せずこれらのファイルを読んでください。

## コマンド

```bash
uv sync                        # 依存関係インストール（Python >=3.12 必須）
cp env.example .env            # 必要なキーだけ設定。ほとんどのソースはキー不要

uv run pytest tests/                        # 全テスト実行（integration マーカー付きの実APIテストは既定で除外）
uv run pytest tests/ -m integration         # 実APIにアクセスするテストだけ実行
uv run pytest tests/test_eia.py             # 単一テストファイル
uv run pytest tests/test_eia.py::test_mock_crude_stocks -v   # 単一テスト

uv run python scripts/yahoo_fetcher.py --tickers 7203.T USDJPY=X --start 2023-01-01
uv run python scripts/meteo_fetcher.py --lat 35.6895 --lon 139.6917 --historical --start 2024-01-01 --end 2024-01-31
```

すべての `*_fetcher.py` は `argparse`（`if __name__ == "__main__"`）により単独実行可能で、かつ Hub 経由でインポート・呼び出しも可能です。APIキーが必要なソースのテストは、`monkeypatch.setenv` でモックキーを入れて HTTP をモックするか、実APIを使うものは `@pytest.mark.integration` を付けてキー未設定時にスキップします — 実際の認証情報がないことを理由に修正を保留しないでください。

テスト基盤（`tests/conftest.py`）: `scripts/` とリポジトリルートを import パスに追加し、`hub`（一時キャッシュ付き Hub）と `make_response`（本物の `requests.Response`）フィクスチャを提供します。integration 以外のテストはネットワーク接続を禁止し、リトライのバックオフ待ち（`api_utils._backoff_sleep`）を省きます。Hub の import 経路そのものは `tests/test_hub_import_isolation.py` がサブプロセス（`scripts/` を path に入れない状態）で検証します。

## アーキテクチャ

### OpenDataHub が唯一の統合ポイント

`scripts/opendata_hub.py` の `OpenDataHub` クラスは、初期化時に `scripts/*_fetcher.py` を全て自動検出し（`_discover_fetchers`、ファイル名サフィックスによる glob — **新しいフェッチャーはファイル命名規則だけで自動登録され、手動の登録作業は不要**）、`importlib.import_module("<name>_fetcher")` でモジュールをオンデマンドにロードします（`sys.modules` にキャッシュされ再実行されないので、`rate_limited` の実行枠などのモジュール状態が保たれる）。Hub はロード時に `scripts/` を `sys.path` に追加するため、フェッチャー内の `from api_utils import ...` はリポジトリルートからのライブラリ利用でも解決できます。各 `get_*` メソッド（例: `get_weather`、`get_pmi`、`get_boj_tankan`）は共通の形をしています:

1. `params` dict を構築 → `CacheManager`（Parquetベース、TTLはソースの変動性により異なる: 天候/AIS/GDELTは数時間、為替/市場データは12〜24時間程度、マクロ/貿易データは1週間〜1ヶ月）を確認。
2. キャッシュミス時は `_cached_fetch` → `_fetch_to_df` がフェッチャーモジュールをロードして `fetch_*`/`compute_*` 関数を呼び出す。
3. 結果が「退化」（`_is_degenerate`: 空、または全カラムが全行null）していればキャッシュをスキップ — 取得失敗を正当な欠損データのようにキャッシュしてはならない。
4. 正規化された Polars DataFrame を返す（`_normalize_df` がソース固有のカラム名を `date`/`value` の契約にマッピング）。

新しいデータソースの追加は `scripts/<name>_fetcher.py` を配置し、Hub に `get_<name>` メソッドを配線する（一般的なケースでは `_cached_fetch` を再利用する）ことで行います — レジストリを編集するのではありません。

### 戻り値の契約 (`_fetch_to_df`)

フェッチャーは DataFrame を返します（pandas も `_coerce_to_polars` で受け付ける）。Hub は `output_file` を渡さず CSV を経由しないので、型（日付など）が保たれます。`None` など DataFrame 以外が返ったら「データ無し」と区別できなくなるため `TypeError` にします。

### Fail Loud, Not Silent（握り潰さない設計）

これは意図的で、設計上の中核原則です（`SKILL.md`、`BACKLOG.md` の v2.2 バグ監査ノート参照）— 取得失敗を「データ無し」と区別不能にしてはいけません。サイレントに空になった外生変数は下流の予測を汚染するためです:

- `api_utils.retry_with_ratelimit` は一時的エラー（ネットワークエラーおよびHTTP 429/5xx、`_is_transient` で判定）**のみ**を `tenacity` でリトライします。プログラムエラー（`KeyError`、`ValueError`、429以外の4xx）は即座に失敗し、無駄な5回リトライと指数バックオフを避けます。
- フェッチャーは取得失敗・HTTP エラー・200 で返るエラーペイロードを例外として送出します。空DataFrameを返してよいのは、API が正常応答で0件を返したと確定した場合だけです。
- `require_api_key` はキー未設定で `MissingApiKeyError`（`RuntimeError` のサブクラス）を送出します。ライブラリ利用者は `from scripts.opendata_hub import MissingApiKeyError` で捕捉します（`scripts.api_utils` から import すると別クラスになり捕まらない）。`sys.exit` はライブラリ経路に置かず、CLI の終了コードへの変換は `cli_entry(main)` だけが行います（`SystemExit` は `get_many` の `except Exception` を素通りしてバッチ全体を落とすため）。
- `Hub.get_many` は失敗を隔離して空DataFrameを返しますが、失敗したラベルと例外は `hub.last_errors` に残ります（空DFが「0件」か「失敗」かはここで区別する）。
- e-Stat の特殊文字（`DATA_INF.NOTE` で定義された秘匿 `X`・該当なし `-` 等）は確定欠測として `value` を null にし、記号を `value_note` に残します。`time_align` は数値化できない値・解析できない日付・一致しないフィルタを例外にします。
- `CacheManager` / `_is_degenerate` は空または全null の結果を絶対にキャッシュしないため、一時的な失敗が「空」の古いキャッシュエントリ経由で以後の呼び出しを汚染することがありません。

フェッチャーや Hub の取得パスを触る際は、「取得失敗が確定した」と「取得に失敗した」の区別を維持してください。

### フェッチャーモジュールの規約

各 `scripts/<name>_fetcher.py` は典型的に以下を持ちます:

- モジュール先頭の `from api_utils import ...`（try/except のフォールバックは不要）。HTTP は `from api_utils import get_with_retry as _get_with_retry`（timeout 付き、429/5xx・接続系のみリトライ）。URL やクエリに API キーが入るソースは `get_with_retry_redacted`（例外メッセージからキーを伏せる）。`requests.get` は呼び出し時に解決されるので、テストの `@patch("<module>.requests.get")`（= requests モジュール自体の `get` の差し替え）がそのまま効きます。
- 認証情報が必要なソース向けの `require_api_key(env_var, site_name, url)` 呼び出し — 未設定なら取得方法を添えて `MissingApiKeyError` を送出します。
- Polars DataFrame を返す `fetch_<name>_data(..., output_file: str | None = None) -> pl.DataFrame` 関数。`output_file` が指定されれば `save_output` で CSV も書き出します（空DFは書かない）。既定の期間は `default_date_range`（UTC）。
- `if __name__ == "__main__": cli_entry(main)` で起動する `argparse` ベースの `main()`（例外は stderr に出して終了コード1）。
- 関数全体に `@retry_with_ratelimit` を付けない（内部の `_get_with_retry` と二重リトライになる）。レート制限が必要なものは `@rate_limited` を使う（スレッド間で共有、ロック付き）。

一部のフェッチャー（例: `eia_fetcher.py`）は、共有REST エンドポイント上の名前付きプリセット用に `SERIES_ALIAS` / ファセットマッピング dict を公開します — エンドポイントがエイリアス間で共有される場合、区別用ファセットはエイリアスごとに明示的に設定する必要があります（過去のバグ: `crude_stocks`/`gasoline_stocks` がこれなしでは混在データをサイレントに返していました）。

### 時系列アラインメント (`scripts/time_align.py`)

`align_frequency` は単一の `date`/`value` 系列（Polars の `group_by_dynamic` 使用）を、設定可能な集約方法で目標周波数にリサンプリングします。`align_many` は複数ソースを共通の日付グリッドに結合し、予測モデルへの供給に使います。1日付あたり複数行を持つソース（例: e-Statの景気動向指数 = 系列 × 表章項目）は、アラインメントの前後で `filter_col`/`filter_val` により単一系列に絞り込む**必要があります**。そうしないと異なる系列の値がサイレントに混ざって集約されます。`align_many` ではソースごとに `filters={名前: (filter_col, filter_val)}` で指定します。日付解析（`parse_dates`、`feature_engineer` と共通）は全行を1つの形式で解析できる場合だけ採用し、解析できない値・数値化できない値・一致しないフィルタは例外にします。

### 並列ファンアウト (`Hub.get_many`)

複数の `get_*` 呼び出しを `ThreadPoolExecutor`（I/Oバウンドのため）で並列実行します。各specの失敗は隔離され、あるソースの例外はバッチ全体を失敗させるのではなく、そのラベルの空DataFrameになります（例外は `hub.last_errors[label]` に入る）。`CacheManager` は同じインスタンスを共有するスレッドから安全に使えるよう、メタデータ更新をロック下で行い、ファイルを一時ファイル経由の `os.replace` で書きます。

## 重要な制約

- Python >=3.12、依存関係・パッケージ管理は `uv` 経由（pip/poetry直接ではない）。
- 内部標準のDataFrameライブラリは pandas ではなく Polars — pandasは相互運用の境界としてのみ登場します（例: `yfinance` は pandas を返し、`_coerce_to_polars` が Polars に変換）。
- 取得したデータの利用条件はソースごとに異なり、本リポジトリの MIT ライセンスの対象**外**です — 出典表記の必須要件、e-Stat/FRED/Open-Meteo の必須表記、商用利用制限に関わる変更を行う前に `docs/DATA_SOURCE_TERMS.md` を確認してください（Open-Meteo の無償枠は非商用限定、`yfinance`/`trendspyg` は非公式・グレーゾーンなライブラリ、ODPT は開発者登録が必須）。
