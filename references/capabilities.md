## 📊 データカテゴリと取得可能なデータ一覧 (Capabilities)

本スキル (`opendata-skill`) は、SCMの需要予測やマーケティング分析に必要な外部要因（市況、天候、トレンド等）を単一のインターフェースで取得できる統合ハブです。

### 1. 📈 経済・金融 (Economy & Finance)
マクロ経済指標や市場データを取得し、需要変動の外部要因として活用します。

*   **EDINET DB (`edinet_fetcher.py`)**
    *   **取得データ**: 日本の上場企業の財務データ (売上高、営業利益、総資産など) および財務比率 (ROE、ROAなど)。
    *   **特徴**: `edinetdb` パッケージを利用して簡単に取得可能。
*   **Yahoo Finance (`yahoo_fetcher.py`)**
    *   **取得データ**: 株価 (日米欧)、為替 (FX)、コモディティ価格 (原油、銅など)、株価指数。OHLCV (Open, High, Low, Close, Volume)。
    *   **特徴**: ETF等への自動フォールバック機能付き。
*   **World Bank (`worldbank_fetcher.py`)**
    *   **取得データ**: 各国のGDP、インフレ率 (CPI)、人口推移、貿易収支など。
    *   **特徴**: `gdp`, `inflation` などのエイリアスで簡単に指定可能。
*   **OECD (`oecd_fetcher.py`)**
    *   **取得データ**: MEI (主要経済指標)、労働市場データなど、先進国の詳細な経済統計。
*   **e-Stat (`estat_fetcher.py`)**
    *   **取得データ**: 日本の政府統計。国勢調査、消費者物価指数 (CPI)、毎月勤労統計、機械受注など。
*   **FRED (`fred_fetcher.py`)**
    *   **取得データ**: 米国のマクロ経済指標。政策金利、失業率、インフレ指標など。
*   **Logistics (`freight_fetcher.py`)**
    *   **取得データ**: バルチック海運指数 (BDI) や物流関連ETFの価格データ。サプライチェーンの逼迫度を示す。

### 2. 🌤️ 環境・インフラ (Environment & Infrastructure)
天候や電力データを取得し、季節性商品やエネルギー消費の分析に活用します。

*   **Open-Meteo (`meteo_fetcher.py`)**
    *   **取得データ**: 過去の気象データおよび予報。気温、降水量、風速、日射量など（1時間ごと／日次）。
    *   **特徴**: APIキー不要で高精度な座標指定が可能。
*   **Open-Meteo Air Quality (`air_quality_fetcher.py`)**
    *   **取得データ**: 大気質データ。PM2.5、NO2、オゾン濃度など。
*   **TEPCO (`power_fetcher.py`)**
    *   **取得データ**: 東京電力管内の電力使用状況。

### 3. 🏙️ 地域・都市 (Regional & Urban)
商圏分析や出店計画、不動産価値の評価に活用します。

*   **MLIT (国土交通省) (`mlit_fetcher.py`)**
    *   **取得データ**: 不動産取引価格、地価公示データ。
*   **PLATEAU (`plateau_fetcher.py`)**
    *   **取得データ**: 3D都市モデルデータ (CityGML/3D Tiles) のメタデータ。
*   **ODPT (`odpt_fetcher.py`)**
    *   **取得データ**: 公共交通オープンデータ。時刻表、リアルタイム運行情報など。

### 4. 📢 トレンド・ソーシャル (Trends & Social)
消費者の関心事やリアルタイムな評判を取得し、突発的な需要変動をキャッチします。

*   **Google Trends (`trends_fetcher.py`)**
    *   **取得データ**: 検索キーワードの相対的関心度 (0-100)。
*   **YouTube (`youtube_fetcher.py`)**
    *   **取得データ**: 動画へのコメント、エンゲージメント（高評価数など）に基づくセンチメント分析。
*   **xAI (Grok) (`x_grok_fetcher.py`)**
    *   **取得データ**: X (旧Twitter) のリアルタイム投稿データ（要Grok API）。
*   **Events (`events_fetcher.py`)**
    *   **取得データ**: 祝日情報、地域のイベントスケジュール。

### 5. 🎯 先行指標・SCリスク (Leading Indicators & SC Risk) — v2.1 新規追加
需要予測モデルの外生変数として最も効く「先行指標」と、サプライチェーン断絶リスクを構造化データで捕捉します。

*   **PMI / ISM / OECD CLI (`pmi_fetcher.py`)**
    *   **取得データ**: FRED経由で製造業新規受注、OECD景気先行指数 (米/日/中/EU)、経済政策不確実性指数。
    *   **特徴**: 需要予測モデルの標準外生変数。製造業PMIの代替・補完として機能。
*   **UN Comtrade (`comtrade_fetcher.py`)**
    *   **取得データ**: HSコード粒度のグローバル貿易フロー。輸入・輸出、相手国別内訳。
    *   **特徴**: サプライ上流の変動を捕捉。e-Stat貿易統計を国際的に補完。
*   **EIA (`eia_fetcher.py`)**
    *   **取得データ**: 米エネルギー情報局の週次原油在庫、天然ガス在庫、精製所稼働率、電力需給。
    *   **特徴**: 「価格」ではなく「需給ファンダ」を先読み。Yahoo先物より先行性高。
*   **GDELT (`gdelt_fetcher.py`)**
    *   **取得データ**: グローバルニュースから抽出された地政学イベント・SC断絶事象の時系列・記事一覧・感情分析。
    *   **特徴**: APIキー不要。スエズ・紅海・台湾海峡などの断絶リスクを定量化。SCM_RISK_THEMESエイリアス付き。
*   **AIS / 港湾混雑 (`ais_fetcher.py`)**
    *   **取得データ**: 主要15港湾 (上海・シンガポール・LA・ロッテルダム・スエズ等) の船舶AIS位置・混雑度。
    *   **特徴**: BDIなどの海運指数は結果指標、AISは**先行指標**。Datalastic/AISHub対応。
*   **日銀 短観 TANKAN (`boj_fetcher.py`)**
    *   **取得データ**: 業況判断DI (大企業/中堅/中小・製造業/全産業、最近・先行き)。日銀時系列統計API経由。
    *   **特徴**: APIキー不要。B2B需要・設備投資の先行シグナル。四半期。`get_boj_tankan()`。
*   **内閣府 景気動向指数 CI/DI (e-Stat `0003446461`)**
    *   **取得データ**: 景気動向指数の先行指数/一致指数/遅行指数 (CI/DI)。月次。
    *   **特徴**: 需要予測の標準的な先行指標。`get_keiki_di()` (e-Stat経由・要ESTAT_API_KEY)。
*   **JNTO 訪日外客数 (e-Stat `0003449064`)**
    *   **取得データ**: 港別 入国外国人の国籍・地域別人数。月次。
    *   **特徴**: インバウンド需要のドライバー。`get_inbound_visitors()` (港×国籍粒度→港次元で集計)。

### 6. 🌾 業界特化データ (Industry-Specific) — v2.1 新規追加

*   **USDA / FAOSTAT (`usda_fetcher.py`)**
    *   **取得データ**: USDA NASS米国農業統計、FAOSTATグローバル作況・在庫・食料需給バランス。
    *   **特徴**: `maff_fetcher` の海外版。食品業界の上流シグナル。
*   **半導体業界 (`semicon_fetcher.py`)**
    *   **取得データ**: 米国「コンピュータ・電子製品」製造業（FRED A34S* 系列）の出荷・新規受注・在庫。半導体単独の系列ではない。Book-to-Bill比（受注/出荷）の自動計算。
    *   **特徴**: WSTS/SEMIは会員制のためFRED公開データ経由。電気機器・精密機器の景気判断。
*   **ENTSO-E (`entsoe_fetcher.py`)**
    *   **取得データ**: 欧州15カ国の電力需給実績・予測、Day-ahead価格、風力・太陽光発電。
    *   **特徴**: TEPCOの欧州版。エネルギーコスト・排出権価格に連動。

### 7. 🌍 グローバルリスク・補完 (Global Risk & Complement) — v2.1 新規追加

*   **USGS Earthquake (`usgs_fetcher.py`)**
    *   **取得データ**: グローバル地震リアルタイム（マグニチュード、位置、深さ、津波フラグ）。
    *   **特徴**: J-SHISは日本特化、こちらは海外工場・サプライヤ拠点評価用。APIキー不要。
*   **NASA FIRMS (`firms_fetcher.py`)**
    *   **取得データ**: 衛星観測による山火事ホットスポット (MODIS/VIIRS)。
    *   **特徴**: 米西海岸・豪州・地中海・シベリアなど主要リスクエリアのプリセット付き。
*   **ECB / BOJ 公的為替 (`official_fx_fetcher.py`)**
    *   **取得データ**: ECB Eurosystem公式日次レート、BOJ/フランクフルター経由の円建公式レート。
    *   **特徴**: Yahooは市場値、こちらは**会計・決算・税務・契約用の公的レート**。

### 8. 🛠️ ユーティリティ (Utilities)
データ統合前の名寄せや、機械学習モデル向けの特徴量生成を行います。

*   **ZipCloud (`zipcode_fetcher.py`)**: 郵便番号から住所への変換。
*   **GSI Maps (`gsi_fetcher.py`)**: 国土地理院APIを用いたジオコーディング（住所・地名から緯度経度への変換）。
*   **National Tax (`corp_fetcher.py`)**: 国税庁APIを用いた法人番号・企業情報の検索。
*   **ML Features (`feature_engineer.py`)**: 取得した時系列データに対し、ラグ変数 (Lag)、移動平均 (Rolling Mean)、カレンダーフラグ（曜日、月末など）を自動生成。
*   **Time Alignment (`time_align.py`)**: 異なる周波数（日次/週次/月次）の外生変数を共通周波数にリサンプリングして横結合 (`align_frequency` / `align_many`)。予測モデルへの covariate 投入前に周波数を揃える。
*   **Parallel Fan-out (`OpenDataHub.get_many`)**: 複数ソースを並列取得 (I/Oバウンドをスレッドで並列化)。1ソースの失敗は隔離（そのラベルは空DF、例外は `hub.last_errors` に残る）。
