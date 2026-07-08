# 🌏 OpenData Skill

**世の中に散在するオープンデータ・外部APIを、単一のクリーンなインターフェース（`OpenDataHub`）に統合するデータ取得ツールキット。**

需要予測（[darts-forecast-skill](https://github.com/iida-masashi) 等）やビジネス分析に「外部要因（市況・天候・トレンド・地政学リスク）」を供給するためのデータパイプラインとして機能します。SCM・マーケティング・経済分析向けに約44のデータソースをカバーしています。

## 特徴

- **44+ データソース統合**: e-Stat / 日銀短観 / RESAS / 不動産情報ライブラリ / PLATEAU / FRED / World Bank / OECD / UN Comtrade / EIA / ENTSO-E / NASA FIRMS / GDELT / AIS港湾混雑 / Open-Meteo / Google Trends / Yahoo Finance ほか
- **Polars First**: 内部データ処理の標準は `polars`（高速・省メモリ）
- **Unified Interface**: `scripts/opendata_hub.py` の `OpenDataHub` が全ソースを統一API化。各ソースは単体CLIとしても実行可能
- **Resilience**: 一時的エラー（HTTP 429/5xx・接続断）のみ自動リトライ。取得失敗を「データ無し」と誤認させない Fail Loud 設計
- **Parallel & Align**: `get_many()` で多ソース並列取得 → `time_align.py` で異周波数の系列を共通周波数に整列し、そのまま予測モデルの外生変数へ

## セットアップ

Python 3.12 以上と [uv](https://docs.astral.sh/uv/) が必要です。

```bash
uv sync

# APIキーが必要なソースを使う場合（多くのソースはキー不要で動きます）
cp env.example .env
# .env を編集して必要なキーだけ設定
```

## クイックスタート

### Python から（推奨: OpenDataHub）

```python
from scripts.opendata_hub import OpenDataHub

hub = OpenDataHub()

df_weather = hub.get_weather(lat=35.6812, lon=139.7671)   # 東京の気象（キー不要）
df_gdp     = hub.get_economic(indicators=["gdp"])          # World Bank（キー不要）
df_tankan  = hub.get_boj_tankan(series="tankan_large_mfg") # 日銀短観 大企業製造業DI（キー不要）
df_pmi     = hub.get_pmi(series="us_new_orders")           # 米製造業新規受注（要 FRED_API_KEY）

# 多ソース並列取得 → 月次に整列して予測モデルの外生変数に
sources = hub.get_many([
    {"label": "weather", "method": "get_weather",    "kwargs": {"lat": 35.68, "lon": 139.77}},
    {"label": "oil",     "method": "get_yahoo",      "kwargs": {"symbol": "CL=F"}},
])
from scripts.time_align import align_many
covariates = align_many(sources, freq="1mo", agg="mean")
```

### CLI から

```bash
uv run python scripts/yahoo_fetcher.py --tickers 7203.T USDJPY=X --start 2023-01-01
uv run python scripts/meteo_fetcher.py --lat 35.6895 --lon 139.6917 --historical
uv run python scripts/trends_fetcher.py --keywords "Python,Rust"
```

詳細な使い方は [`references/usage_guide.md`](references/usage_guide.md)、取得可能なデータの全一覧は [`references/capabilities.md`](references/capabilities.md) を参照してください。

## ドキュメント

| ファイル | 内容 |
|---|---|
| [`SKILL.md`](SKILL.md) | AIエージェント向けのスキル定義（エントリポイント） |
| [`references/capabilities.md`](references/capabilities.md) | 取得可能データの全カタログ |
| [`references/usage_guide.md`](references/usage_guide.md) | CLI / `OpenDataHub` の使い方 |
| [`references/INDUSTRY_GUIDE.md`](references/INDUSTRY_GUIDE.md) | 産業別の推奨データソースガイド |
| [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) | 機能・非機能要件 |
| [`docs/DATA_SOURCE_TERMS.md`](docs/DATA_SOURCE_TERMS.md) | **各データソースの利用規約・出典表記ガイド（必読）** |

## テスト

```bash
uv run pytest tests/
```

外部APIに依存するテストは、対応するAPIキーが未設定の場合は自動スキップされます。

## ⚠️ 外部データサービスの利用について

本ソフトウェア自体は MIT ライセンスですが、**取得したデータの利用条件は各提供元の規約に従います**。特に：

- **e-Stat / FRED / Open-Meteo** には規約上の**必須表記**があります
- **Open-Meteo** の無償APIは**非商用利用限定**です
- **yfinance / pytrends** は非公式ライブラリであり、Yahoo!/Google の規約上グレーです（研究・個人利用推奨）
- **ODPT** は開発者登録と規約同意が必須です

詳細は [`docs/DATA_SOURCE_TERMS.md`](docs/DATA_SOURCE_TERMS.md) を必ず確認してください。商用利用の際は各提供元の一次情報の再確認を推奨します。

## ライセンス

[MIT License](LICENSE)
