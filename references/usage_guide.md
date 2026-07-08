## 🚀 使い方 (Usage Guide)

### 1. 統合ハブ (OpenDataHub) の利用 (推奨)
Pythonスクリプトから複数のデータソースにアクセスする場合、`OpenDataHub` を使用するとインターフェースが統一され、最も効率的です。

```python
from scripts.opendata_hub import OpenDataHub

# ハブの初期化（内部で環境変数を自動読み込み）
hub = OpenDataHub()

# 天候データの取得 (東京駅付近)
df_weather = hub.get_weather(lat=35.6812, lon=139.7671)

# 経済指標の取得 (日本のGDP)
df_gdp = hub.get_economic(indicators=["gdp"])

# グローバルマクロ指標のプリセット取得 (例: 欧州)
df_eu_macro = hub.get_global_macro(region="EU")

# 産業別コモディティ価格プロキシの取得 (例: 自動車産業に必要な原油・鉄鋼等)
df_auto_commodities = hub.get_commodity_proxies(industry="輸送用機器")

# 日本国内データの深化 (e-Stat) - kwargsで追加パラメータ(cdArea等)を指定可能
df_estat_tokyo = hub.get_estat(stats_data_id="0003425251", cdArea="13000")
```

### 2. 個別スクリプトのコマンドライン実行 (CLI)
特定のデータを素早くCSVとして抽出したい場合は、各スクリプトを直接実行します。

**例1: 株価・為替の取得 (トヨタ自動車とドル円)**
```bash
uv run python scripts/yahoo_fetcher.py --tickers 7203.T USDJPY=X --start 2023-01-01
```

**例2: 過去の気象データの取得 (東京)**
```bash
uv run python scripts/meteo_fetcher.py --lat 35.6895 --lon 139.6917 --historical
```

**例3: Googleトレンドの比較 ("Python" vs "Rust")**
```bash
uv run python scripts/trends_fetcher.py --keywords "Python,Rust"
```

**例4: 地価データの取得 (東京都千代田区)**
```bash
uv run python scripts/mlit_fetcher.py --year 2023 --pref 13 --city 13101
```

### 3. 高度な分析ツール

**相関分析 (`correlation_analyzer.py`)**
異なる2つのデータセット（例：天候と電力消費）間の相関関係を分析します。
```bash
uv run python scripts/correlation_analyzer.py weather.csv --col1 temperature power.csv --col2 usage
```

**データサジェスター (`data_suggester.py`)**
「何を分析すべきか」迷った際に、`references/INDUSTRY_GUIDE.md` をキーワード検索して目的に適したデータソースを提案します。
```bash
uv run python scripts/data_suggester.py "円安が製造業の輸出に与える影響を分析したい"
```

---

## 🆕 v2.1 新規フェッチャーの使用例 (SCM先行指標・グローバルリスク)

### OpenDataHub 経由 (推奨)
```python
from scripts.opendata_hub import OpenDataHub
hub = OpenDataHub()

# 先行指標
df_pmi = hub.get_pmi(series="us_new_orders")           # 米製造業新規受注
df_cli = hub.get_pmi(series="oecd_cli_jp")              # 日本OECD景気先行指数
df_trade = hub.get_comtrade(reporter="JP", partner="CN", hs_code="8542")  # 日中IC貿易
df_oil = hub.get_eia(series="crude_stocks")             # 米原油在庫（週次）

# SC断絶リスク
df_gdelt = hub.get_gdelt(query="red sea shipping", theme="supply_chain")
df_ais = hub.get_ais(port="shanghai")                   # 上海港混雑度
df_quake = hub.get_usgs_earthquakes(min_magnitude=5.0)  # M5以上の直近地震
df_fire = hub.get_firms(region="us_west", days=7)       # 米西海岸の山火事

# 業界特化
df_agri = hub.get_agri(source="faostat", commodity="wheat", area="WLD")
df_semi = hub.get_semicon(series="book_to_bill")        # 半導体B2B比
df_power = hub.get_entsoe(data_type="day_ahead_price", country="DE")

# 公的為替 (会計・契約用)
df_fx = hub.get_official_fx(source="ecb", currency="JPY")

# 日本の先行指標プリセット
df_tankan = hub.get_boj_tankan(series="tankan_large_mfg")  # 日銀短観 大企業製造業DI
df_keiki = hub.get_keiki_di()                              # 内閣府 景気動向指数(CI/DI)
df_inbound = hub.get_inbound_visitors()                    # JNTO 訪日外客数(港×国籍)
```

### 3. 複数ソース並列取得とアラインメント (covariate パイプライン)
```python
# 複数ソースを並列に取得（1ソースの失敗は隔離され空DFになる）
sources = hub.get_many([
    {"label": "weather", "method": "get_weather", "kwargs": {"lat": 35.68, "lon": 139.77}},
    {"label": "tankan",  "method": "get_boj_tankan", "kwargs": {"series": "tankan_large_mfg"}},
    {"label": "oil",     "method": "get_yahoo", "kwargs": {"symbol": "CL=F"}},
])

# 異なる周波数を月次に揃えて横結合 → 予測モデルの外生変数に
from scripts.time_align import align_many
covariates = align_many(sources, freq="1mo", agg="mean")  # date列 + weather/tankan/oil列
```

### CLI: 周波数アライン / 日銀短観
```bash
uv run python scripts/time_align.py --input weather.csv --freq 1mo --agg mean --out monthly.csv
uv run python scripts/boj_fetcher.py --series tankan_large_mfg --start 202001
```

### CLI 直接実行
```bash
# PMI・先行指標
uv run python scripts/pmi_fetcher.py --series oecd_cli_us --start 2020-01-01

# 貿易フロー (半導体輸入)
uv run python scripts/comtrade_fetcher.py --reporter JP --partner CN --hs 8542 --flow M

# エネルギー在庫
uv run python scripts/eia_fetcher.py --series natgas_storage --freq weekly

# SC断絶イベント
uv run python scripts/gdelt_fetcher.py --query "port congestion" --theme port_congestion

# 港湾混雑
uv run python scripts/ais_fetcher.py --port singapore

# 山火事
uv run python scripts/firms_fetcher.py --region california --days 7

# ENTSO-E電力価格
uv run python scripts/entsoe_fetcher.py --type day_ahead_price --country DE

# ECB公式為替
uv run python scripts/official_fx_fetcher.py --source ecb --currency JPY
```

### 必要な追加APIキー (.env)
```env
# FRED (PMI, Semiconductor用)
FRED_API_KEY=your_key

# EIA (米エネルギー)
EIA_API_KEY=your_key

# UN Comtrade (Premiumのみ。無料はキー不要)
COMTRADE_API_KEY=your_key  # optional

# AIS
DATALASTIC_API_KEY=your_key   # or
AISHUB_USERNAME=your_username

# USDA Quick Stats (FAOSTATはキー不要)
USDA_API_KEY=your_key

# ENTSO-E
ENTSOE_API_KEY=your_key

# NASA FIRMS
NASA_FIRMS_API_KEY=your_key
```

APIキー不要のもの: **GDELT, USGS, FAOSTAT, ECB**

---

## ⚙️ セットアップと環境変数

一部のAPI（e-Stat、RESASなど）を使用するには、プロジェクトルートの `.env` ファイルにAPIキーを設定する必要があります。

```env
# Required for e-Stat (Gov Statistics)
ESTAT_API_KEY=your_app_id_here

# Required for RESAS (Regional Economy)
RESAS_API_KEY=your_api_key_here

# Required for MLIT (Land Price) - Optional for some endpoints
MLIT_API_KEY=your_api_key_here

# Required for X (Twitter) search via Grok (x_grok_fetcher)
XAI_API_KEY=your_grok_api_key
```