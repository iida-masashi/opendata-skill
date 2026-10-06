# 🌏 OpenData Skill

**世の中に散在するオープンデータ・外部APIを、単一のクリーンなインターフェース（`OpenDataHub`）に統合するデータ取得ツールキットです。**

需要予測（[darts-forecast-skill](https://github.com/iida-masashi) 等）やビジネス分析に、市況・天候・トレンド・地政学リスクといった「外部要因」を安定的に供給するデータパイプラインとして機能します。SCM（サプライチェーンマネジメント）、マーケティング、経済分析の各領域を対象に、約43のデータソースを一つのインターフェースでカバーしており、個別のAPI仕様を都度調査・実装する工数を削減いたします。

## ご提供価値

オープンデータ・外部APIの活用には、本来「データソースごとの仕様調査」「認証方式の違いへの対応」「取得失敗時のエラーハンドリング」「異なる周波数のデータを分析可能な形へ整える前処理」といった、分析の本質とは直接関係のない付随作業が数多く発生します。本ツールキットは、これらの付随作業を一括して引き受けることで、利用者が「どのデータを、どう分析に活かすか」という本質的な検討に集中できる環境を提供いたします。

- **統合インターフェース**: 40以上のデータソースを `OpenDataHub` 経由で統一的に呼び出し可能。データソースごとの実装差異を意識する必要がありません。各ソースは単体のCLIツールとしても実行できるため、簡易な動作確認やアドホックなデータ抽出にも対応します。
- **高い信頼性（Fail Loud設計）**: 一時的なエラー（HTTP 429/5xx・接続断）のみを自動的にリトライし、それ以外のエラー（HTTP 4xx、HTTP 200 で返るエラー応答、解析できない値など）は例外として表面化させます。空のデータが返るのは提供元が正常に「0件」と応答した場合だけで、取得失敗を「データが存在しない」と誤認させない設計とすることで、欠損した外部要因が予測モデルに気づかれずに混入する事態を防ぎます。
- **高速なデータ処理**: 内部処理には `pandas` ではなく `polars` を採用し、高速かつ省メモリなデータハンドリングを実現しています。
- **並列取得と周波数統合**: `get_many()` により複数データソースを並列取得し、`time_align.py` で日次・週次・月次といった異なる周波数の系列を共通の周波数へ整列。そのまま予測モデルの外生変数として投入可能な形に整えます。
- **ローカルキャッシュ**: 取得済みデータは Parquet形式でローカルキャッシュされ、同一条件での再取得コスト（API呼び出し回数・待機時間）を削減します。キャッシュの有効期限はデータの変動性に応じてソースごとに調整されています。

## 想定される利用シーン

- **需要予測モデルへの外生変数供給**: 気象、為替・コモディティ価格、景気動向指数など、需要変動要因となる系列を予測モデルにそのまま投入できる形式で取得。
- **サプライチェーンリスクの定量把握**: 港湾混雑、地政学イベント、地震・山火事といったサプライチェーン断絶リスクを、構造化データとして継続的にモニタリング。
- **マーケティング・商圏分析**: 検索トレンド、人口動態、地価情報などを組み合わせた出店計画・需要地域の見極め。
- **業界別の先行指標モニタリング**: 日銀短観、PMI、半導体Book-to-Bill比など、業種ごとに有効性の高い先行指標を横断的に取得。

産業別にどのデータソースが有効かは [`references/INDUSTRY_GUIDE.md`](references/INDUSTRY_GUIDE.md) に整理しております。製造業・物流/SCM・小売/マーケティング・建設/不動産・金融/保険・農業・公共/研究の各領域について、ユースケース単位で推奨データソースをご案内しています。

## セットアップ

Python 3.12 以上と [uv](https://docs.astral.sh/uv/) が必要です。

```bash
uv sync

# APIキーが必要なソースを使う場合（大半のソースはキー不要でご利用いただけます）
cp env.example .env
# .env を編集し、利用予定のソースに対応するキーのみ設定してください
```

既存の環境を更新した際に `uv sync` 後 `No module named 'urllib3.exceptions'` が出る場合は、`uv sync --reinstall-package urllib3` で復旧できます（削除された依存 urllib3-future が urllib3 のファイルを巻き込んで消すため）。

APIキーが未設定のまま該当ソースを呼び出した場合、「どのサイトで、どのように取得すべきか」を案内するメッセージ付きで `MissingApiKeyError` が送出されます（CLI ではメッセージを表示して終了コード1で終了）。設定漏れの有無を都度コードで確認いただく必要はありません。

## クイックスタート

### Python から（推奨: OpenDataHub）

```python
from scripts.opendata_hub import MissingApiKeyError, OpenDataHub

hub = OpenDataHub()

df_weather = hub.get_weather(lat=35.6812, lon=139.7671)   # 東京の気象（キー不要）
df_gdp     = hub.get_economic(indicators=["gdp"])          # World Bank（キー不要）
df_tankan  = hub.get_boj_tankan(series="tankan_large_mfg") # 日銀短観 大企業製造業DI（キー不要）
try:
    df_pmi = hub.get_pmi(series="us_new_orders")           # 米製造業新規受注（要 FRED_API_KEY）
except MissingApiKeyError as e:
    print(e)                                               # キーの取得方法が表示される

# 多ソース並列取得 → 月次に整列して予測モデルの外生変数に
sources = hub.get_many([
    {"label": "weather", "method": "get_weather",    "kwargs": {"lat": 35.68, "lon": 139.77}},
    {"label": "oil",     "method": "get_yahoo",      "kwargs": {"symbol": "CL=F"}},
])
from scripts.time_align import align_many
covariates = align_many(sources, freq="1mo", agg="mean")
failed = hub.last_errors  # 取得に失敗したラベル → 例外（空DFが「0件」か「失敗」かを区別）
```

### CLI から

```bash
uv run python scripts/yahoo_fetcher.py --tickers 7203.T USDJPY=X --start 2023-01-01
uv run python scripts/meteo_fetcher.py --lat 35.6895 --lon 139.6917 --historical --start 2024-01-01 --end 2024-01-31
uv run python scripts/trends_fetcher.py --keywords "Python,Rust"
```

より詳細な使い方（産業別プリセット、周波数アラインメント、相関分析ツール等）は [`references/usage_guide.md`](references/usage_guide.md) をご参照ください。

## 取得可能なOpenDataの一覧

以下、カテゴリ別に主要なデータソースをご紹介いたします。全ソースの詳細な引数・特徴・関連メソッドは [`references/capabilities.md`](references/capabilities.md) に一覧化しております。

### 📈 経済・金融

企業業績、市場動向、マクロ経済指標など、財務・投資判断や景気動向把握に資するデータ群です。

| データソース | 取得データ | 主な用途 |
|---|---|---|
| EDINET DB (`edinet_fetcher.py`) | 上場企業の財務データ（売上高・営業利益・総資産等）および財務比率（ROE・ROA等） | 企業分析、与信・投資判断 |
| Yahoo Finance (`yahoo_fetcher.py`) | 株価（日米欧）・為替（FX）・コモディティ価格・株価指数（OHLCV） | 市況モニタリング、原材料コスト分析 |
| World Bank (`worldbank_fetcher.py`) | 各国のGDP・インフレ率（CPI）・人口推移・貿易収支 | 国際比較、マクロ経済分析 |
| OECD (`oecd_fetcher.py`) | 主要先進国の詳細経済統計（MEI主要経済指標、労働市場データ等） | 先進国間の景気比較 |
| e-Stat (`estat_fetcher.py`) | 日本の政府統計（国勢調査・消費者物価指数・毎月勤労統計・機械受注等） | 国内市場動向の把握 |
| FRED (`fred_fetcher.py`) | 米国マクロ経済指標（政策金利・失業率・インフレ指標等） | 米国景気動向の把握 |
| 海運 (`freight_fetcher.py`) | バルチック海運指数（BDI）・物流関連ETF価格 | サプライチェーン逼迫度の把握 |

### 🌤️ 環境・インフラ

天候・電力といった、季節性商品の需要やエネルギーコストに直結するデータ群です。

| データソース | 取得データ | 主な用途 |
|---|---|---|
| Open-Meteo (`meteo_fetcher.py`) | 過去の気象データおよび予報（気温・降水量・風速・日射量、時間別/日次） | 季節性商品の需要予測、配送計画 |
| Open-Meteo Air Quality (`air_quality_fetcher.py`) | 大気質データ（PM2.5・NO2・オゾン濃度等） | 環境モニタリング |
| TEPCO (`power_fetcher.py`) | 東京電力管内の電力使用状況 | エネルギーコスト最適化 |

### 🏙️ 地域・都市

商圏分析、出店計画、不動産価値評価に資するデータ群です。

| データソース | 取得データ | 主な用途 |
|---|---|---|
| MLIT 不動産情報ライブラリ (`mlit_fetcher.py`) | 不動産取引価格・地価公示データ | 不動産評価、出店・拠点選定 |
| PLATEAU (`plateau_fetcher.py`) | 3D都市モデルデータ（CityGML/3D Tiles） | 都市計画、シミュレーション |
| ODPT (`odpt_fetcher.py`) | 公共交通オープンデータ（時刻表・リアルタイム運行情報） | 交通アクセス分析 |

RESAS API は 2025-03-24 に提供を終了したため、本ツールキットでは扱っておりません。人口構成・事業所数・企業数は e-Stat（`estat_fetcher.py`）、不動産取引価格は不動産情報ライブラリ（`mlit_fetcher.py`）で取得いただけます（RESAS API 公式の代替案内に準拠）。

### 📢 トレンド・ソーシャル

消費者の関心動向やリアルタイムの評判を捉え、突発的な需要変動を早期に検知するためのデータ群です。

| データソース | 取得データ | 主な用途 |
|---|---|---|
| Google Trends (`trends_fetcher.py`) | 検索キーワードの相対的関心度（0〜100）。[trendspyg](https://github.com/flack0x/trendspyg) の http エンジンで取得（Chrome 不要）。1〜5語を同一スケールで比較可能。短時間に多数の要求を送ると Google が HTTP 429 で拒否し、しばらく取得できなくなります | 需要予測、商品・ブランドの関心度把握 |
| YouTube (`youtube_fetcher.py`) | 動画コメント・エンゲージメント（高評価数等）によるセンチメント | 消費者反応の定性把握 |
| xAI Grok (`x_grok_fetcher.py`) | X（旧Twitter）の投稿データ。xAI Responses API の X 検索ツール（`x_search`）で直近30日を検索し、出典（citation）の無い結果はエラーにする（要 Grok API） | リアルタイムの世論・評判モニタリング |
| Events (`events_fetcher.py`) | 祝日情報・地域のイベントスケジュール | カレンダー効果を考慮した需要分析 |

### 🎯 先行指標・サプライチェーンリスク

需要予測モデルの外生変数として特に有効性の高い「先行指標」と、サプライチェーン断絶リスクを構造化データとして捕捉するデータ群です。

| データソース | 取得データ | 主な用途 |
|---|---|---|
| PMI / ISM / OECD CLI (`pmi_fetcher.py`) | 製造業新規受注・景気先行指数（米/日/中/EU）・経済政策不確実性指数（FRED経由。ISM PMI の系列は FRED から削除済みのため取得不可） | 製造業の景況感把握、需要予測モデルの標準的な外生変数 |
| UN Comtrade (`comtrade_fetcher.py`) | HSコード粒度のグローバル貿易フロー（輸出入、相手国別内訳） | サプライ上流の変動把握 |
| EIA（米エネルギー情報局） (`eia_fetcher.py`) | 米原油/天然ガス在庫・精製所稼働率・電力需給 | エネルギー需給ファンダメンタルズの先読み |
| GDELT (`gdelt_fetcher.py`) | グローバルニュースから抽出した地政学イベント・SC断絶事象（時系列・感情分析付き、キー不要） | 地政学リスクの定量化 |
| AIS 港湾混雑 (`ais_fetcher.py`) | 主要15港湾（上海・シンガポール・LA・ロッテルダム・スエズ等）の船舶位置・混雑度 | 海運指数に先行する混雑状況の把握 |
| 日銀短観 (`boj_fetcher.py`) | 業況判断DI（大企業/中堅/中小・製造業/全産業、キー不要） | B2B需要・設備投資の先行シグナル |
| 内閣府 景気動向指数（e-Stat経由） | CI/DI（先行・一致・遅行指数） | 景気の転換点の把握 |
| JNTO 訪日外客数（e-Stat経由） | 港別・国籍別の入国外国人数 | インバウンド需要の把握 |

### 🌾 業界特化データ

| データソース | 取得データ | 主な用途 |
|---|---|---|
| USDA / FAOSTAT (`usda_fetcher.py`) | 米国農業統計・グローバル作況・食料需給バランス | 食品業界の上流シグナル把握 |
| 半導体業界 (`semicon_fetcher.py`) | 米国「コンピュータ・電子製品」製造業の出荷・新規受注・在庫（FRED／半導体単独の系列ではない）、Book-to-Bill比の自動計算 | 電気機器・精密機器の景気判断 |
| ENTSO-E (`entsoe_fetcher.py`) | 欧州15カ国の電力需給実績・予測、Day-ahead価格、風力・太陽光発電 | 欧州エネルギーコスト・排出権価格の連動把握 |

### 🌍 グローバルリスク・補完データ

| データソース | 取得データ | 主な用途 |
|---|---|---|
| USGS Earthquake (`usgs_fetcher.py`) | グローバル地震リアルタイムデータ（マグニチュード・位置・深さ・津波フラグ、キー不要） | 海外工場・サプライヤー拠点のリスク評価 |
| NASA FIRMS (`firms_fetcher.py`) | 衛星観測による山火事ホットスポット（MODIS/VIIRS） | 主要リスクエリアのモニタリング |
| ECB / BOJ 公的為替 (`official_fx_fetcher.py`) | 会計・決算・税務・契約用の公的参照レート | 決算・契約実務における公式レートの確認 |

### 🛠️ ユーティリティ

| データソース | 取得データ | 主な用途 |
|---|---|---|
| ZipCloud (`zipcode_fetcher.py`) | 郵便番号から住所への変換 | 住所データの名寄せ |
| GSI Maps (`gsi_fetcher.py`) | ジオコーディング（住所・地名から緯度経度への変換） | 位置情報を伴う分析の前処理 |
| National Tax 法人番号システム (`corp_fetcher.py`) | 法人番号・企業情報の検索 | 取引先・競合の企業情報照会 |
| ML Features (`feature_engineer.py`) | 時系列データへのラグ変数・移動平均・カレンダーフラグの自動生成 | 予測モデル向け特徴量エンジニアリング |
| Time Alignment (`time_align.py`) | 異なる周波数の外生変数を共通周波数へリサンプリング・横結合 | 予測モデルへのcovariate投入前の周波数統一 |

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
uv run pytest tests/                 # モックテストのみ（ネットワーク不要）
uv run pytest tests/ -m integration  # 実APIにアクセスするテスト
```

既定の実行では、実APIにアクセスするテスト（`integration` マーカー）を除外し、それ以外のテストのネットワーク接続を禁止しています。実APIテストは対応するAPIキーが未設定の場合に自動的にスキップされます。

## ⚠️ 外部データサービスのご利用にあたって

本ソフトウェア自体はMITライセンスにて提供しておりますが、**取得したデータそのものの利用条件は、各データ提供元の規約に従うものとします**。ご利用にあたっては、特に以下の点にご留意ください。

- **e-Stat / FRED / Open-Meteo** には、規約上の**必須表記**が定められています。
- **Open-Meteo** の無償APIは、**非商用利用限定**とされています。
- **yfinance / trendspyg** は非公式ライブラリであり、Yahoo!/Googleの規約上グレーな位置づけとなります（研究・個人利用の範囲での利用を推奨いたします）。
- **ODPT** のご利用には、開発者登録および規約への同意が必須です。

商用利用をご検討の際は、各データ提供元の一次情報を必ず再確認いただくとともに、詳細は [`docs/DATA_SOURCE_TERMS.md`](docs/DATA_SOURCE_TERMS.md) を必ずご確認ください。

## ライセンス

[MIT License](LICENSE)
