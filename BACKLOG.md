# BACKLOG: opendata-skill の今後

## 1. ~~API キー設定の自動検証機能の追加~~ [DONE]
- ~~各フェッチャーが実行直前に `.env` 内の必須 API キーの有無をチェックし、不足している場合はユーザーに「どのサイトで、どの設定で取得すべきか」を自動提示する機能を強化する。~~ (2026/04/14 実装完了)

## 2. ~~API レートリミット制御層 (Rate Limiter) の導入~~ [DONE]
- ~~OECD の新 API や e-Stat など、短時間での大量リクエストに厳しいソースに対し、自動で待機（Sleep）を入れる、あるいはリクエストを分散させる制御ロジックの実装。~~ (2026/04/14 実装完了)

## 3. ~~グローバルマクロ指標プリセットの拡大~~ [DONE]
- ~~現在の OECD / World Bank 連携をベースに、中国 (NBS) や欧州 (Eurostat) などの主要経済圏のデータを、`OpenDataHub` からワンクリックで取得できるプリセットをさらに追加する。~~ (2026/04/14 実装完了)

## 4. ~~自動データクリーニング・補完機能の強化~~ [DONE]
- ~~特徴量生成 (`feature_engineer.py`) において、欠損値のインテリジェントな補完（線形補間や季節性を考慮した補完）を Polars ネイティブで高速に実行する機能。~~ (2026/04/14 実装完了)

---

## v2.1: SCM先行指標・グローバルリスク拡張 (2026/04/18 完了)

### ✅ 高インパクト (先行指標 — 予測精度に直結)
- ~~**PMI / ISM / OECD CLI** (`pmi_fetcher.py`): 製造業先行指標~~ [DONE]
- ~~**UN Comtrade** (`comtrade_fetcher.py`): HSコード粒度のグローバル貿易フロー~~ [DONE]
- ~~**EIA** (`eia_fetcher.py`): 米エネルギー需給ファンダ~~ [DONE]
- ~~**GDELT** (`gdelt_fetcher.py`): 地政学・SC断絶イベント~~ [DONE]

### ✅ 中インパクト (業界特化)
- ~~**AIS / 港湾混雑** (`ais_fetcher.py`): BDIの先行指標~~ [DONE]
- ~~**USDA / FAOSTAT** (`usda_fetcher.py`): 農業・食品グローバル~~ [DONE]
- ~~**半導体 (WSTS/SEMI代替)** (`semicon_fetcher.py`): 出荷・B2B比~~ [DONE]
- ~~**ENTSO-E** (`entsoe_fetcher.py`): 欧州電力需給~~ [DONE]

### ✅ 補完 (既存の隙間埋め)
- ~~**USGS Earthquake** (`usgs_fetcher.py`): グローバル地震~~ [DONE]
- ~~**NASA FIRMS** (`firms_fetcher.py`): 山火事リアルタイム~~ [DONE]
- ~~**ECB / BOJ 公的為替** (`official_fx_fetcher.py`): 会計用公式レート~~ [DONE]

---

---

## v2.2: 堅牢化・日本先行指標・バグ監査 (2026-06-27 完了)

### ✅ バグ監査 (38件修正 / 確証39・棄却8)
- ~~壊れフェッチャー5本: corp(XML)/comtrade(World=0)/ais(経度符号)/eia(facet分離)/jshis(震度コード)~~ [DONE]
- ~~静かに壊す系: feature_engineer(日付parse)/odpt(ネストJSON)/worldbank(部分期間)/semicon(ゼロ除算)~~ [DONE]
- ~~retry述語を 429/5xx・接続系のみに限定（全Exception 5回リトライを廃止）~~ [DONE]
- ~~429リトライ未対応のRESTフェッチャー5本＋trends(pytrends内蔵retry)~~ [DONE]
- ~~entsoe processType必須化 / oecd retry有効化 / fred naive datetime / estat CLI配線＋$重複列 / gdelt空timeline~~ [DONE]
- ~~パッケージング欠落(python-dotenv/matplotlib/seaborn/google-api-python-client)~~ [DONE]

### ✅ 機能追加
- ~~**握り潰し停止＋非退化検証**: `_csv_to_df`がパース失敗を空DFに化けさせず送出。`_is_degenerate`でない場合のみキャッシュ~~ [DONE]
- ~~**temp CSVラウンドトリップ廃止**: `_fetch_to_df`が戻り値DFを優先消費（型保持）。temp名ユニーク化で並列競合防止~~ [DONE]
- ~~**周波数アライン層** (`time_align.py`): `align_frequency`/`align_many`。異周波数covariateの共通グリッド化~~ [DONE]
- ~~**Hub並列ファンアウト** (`get_many`): スレッドプール並列・失敗隔離~~ [DONE]
- ~~**日銀短観** (`boj_fetcher.py`): 業況判断DI。BOJ時系列API・キー不要~~ [DONE]
- ~~**内閣府 景気動向指数** (`get_keiki_di`, e-Stat 0003446461): CI/DI先行指数~~ [DONE]
- ~~**JNTO 訪日外客数** (`get_inbound_visitors`, e-Stat 0003449064): 港別国籍内訳~~ [DONE]

---

## 次期候補 (v2.3)

1. **海運運賃指数の詳細化**: Freightos Baltic Index (FBX), Drewry WCI, SCFI の統合
2. **クレジット・信用指標**: Moody's Analytics, CDSスプレッド
3. **企業サプライヤーマッピング**: Bloomberg SPLC / FactSet Supply Chain 代替のオープンソース
4. **気候/ESG指標**: NOAA Climate Data, EU ETS排出権価格
5. **Pandemic/Health**: WHO Global Health Observatory API
6. **景気動向指数/訪日外客数のプリセット深化**: `get_keiki_di`/`get_inbound_visitors`に series/国フィルタ引数を追加し、`time_align`へ直結可能にする（現状は呼び出し側で`filter_col`指定が必要）
