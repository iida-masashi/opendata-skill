# データソース利用規約・出典表記ガイド

本スキルは多数の外部データソースに接続します。**本ソフトウェア自体のライセンス（MIT）と、取得したデータの利用条件は別物です。** データの利用・再配布・商用利用の可否は各提供元の規約に従ってください。規約は変更されることがあります — 特に商用利用の前には必ず一次情報を確認してください。

- 最終確認日: 2026-07-08
- APIキーは全て環境変数（`.env`）で管理します。`env.example` を参照。キーをコミットしないでください。

---

## 1. 必須の出典表記があるソース

以下は規約上、成果物への表記が**義務**とされているものです。

### e-Stat（政府統計の総合窓口）
`estat_fetcher` / `estat_id_searcher` / `trade_fetcher` が使用。API利用規約により以下の文言の掲載が必要です：

> このサービスは、政府統計総合窓口(e-Stat)のAPI機能を使用していますが、サービスの内容は国によって保証されたものではありません。

加えて、利用した統計調査名の出典明記（例：「出典：総務省『家計調査』（e-Stat）を加工して作成」）が必要です。

### FRED（セントルイス連銀）
`fred_fetcher` / `pmi_fetcher` / `semicon_fetcher` が使用。FRED API Terms of Use により以下の文言の掲載が必要です：

> This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis.

FRED上の一部系列は第三者（S&P、ISM等）のライセンス対象です。系列ごとの利用条件に注意してください。

### Open-Meteo（気象・大気質・洪水）
`meteo_fetcher` / `air_quality_fetcher` / `river_fetcher` が使用。

- 無償APIは**非商用利用限定**です。商用利用には有償プランの契約が必要です。
- データは CC BY 4.0。出典表記（例：「Weather data by Open-Meteo.com」）が必要です。
- 大気質データは Copernicus CAMS 由来、洪水データは GloFAS（Copernicus EMS）由来のため、Copernicus の帰属表示（例：「Contains modified Copernicus Atmosphere Monitoring Service information」）も推奨されます。

---

## 2. ソース別一覧

### 日本の政府・公的機関

| ソース | フェッチャー | キー | 利用条件の要点 |
|---|---|---|---|
| e-Stat API | `estat_fetcher` ほか | `ESTAT_API_KEY` | 上記の必須表記＋統計名の出典明記 |
| 内閣府 祝日CSV | `holiday_fetcher` | 不要 | 公開データ。出典明記を推奨 |
| 国税庁 法人番号Web-API | `corp_fetcher` | `CORP_API_KEY` | 利用規約に同意しアプリケーションIDを取得。出典明記 |
| 日本銀行 時系列統計 | `boj_fetcher` / `official_fx_fetcher` | 不要 | 出典明記（「日本銀行時系列統計データ検索サイト」） |
| RESAS API | `resas_fetcher` | `RESAS_API_KEY` | 利用規約に従い出典明記（「RESAS（地域経済分析システム）を加工して作成」）。2026-07時点で提供継続を確認済み |
| 不動産情報ライブラリ（国交省） | `mlit_fetcher` | `MLIT_API_KEY` | 申請制。利用規約に従い出典明記 |
| G空間情報センター / PLATEAU | `plateau_fetcher` | 不要 | **データセットごとにライセンスが異なる**（多くは CC BY 4.0 または政府標準利用規約）。取得したデータセットの条件を個別確認 |
| 国土地理院 住所検索API | `gsi_fetcher` | 不要 | 国土地理院コンテンツ利用規約。出典「国土地理院」明記 |
| J-SHIS（防災科研） | `jshis_fetcher` | 不要 | 利用規約に従い出典明記 |
| 農水省 食品価格動向 | `maff_fetcher` | 不要 | 公開データ。出典明記を推奨 |
| e-Govデータポータル (CKAN) | `ckan_fetcher` | 不要 | 政府標準利用規約 2.0（CC BY 4.0 互換）。データセットごとの条件も確認 |
| 公共交通オープンデータセンター (ODPT) | `odpt_fetcher` | `ODPT_API_KEY` | **開発者登録と規約同意が必須**。商用利用・再配布はデータ提供事業者ごとの条件に従う |
| 東京電力 でんき予報CSV | `power_fetcher` | 不要 | TEPCOが公開するCSVを直接取得。サイト利用条件に従い出典明記。仕様変更で取得不能になるリスクあり |
| EDINET（金融庁） | `edinet_fetcher` | `EDINETDB_API_KEY` | EDINET API利用規約に従う。`edinetdb` ライブラリ経由のためライブラリ側の条件も確認 |

### 海外の公的機関・国際機関

| ソース | フェッチャー | キー | 利用条件の要点 |
|---|---|---|---|
| FRED | `fred_fetcher` ほか | `FRED_API_KEY` | 上記の必須表記 |
| World Bank | `worldbank_fetcher` | 不要 | CC BY 4.0。出典明記 |
| OECD SDMX API | `oecd_fetcher` | 不要 | OECD利用規約。出典明記 |
| UN Comtrade | `comtrade_fetcher` | `COMTRADE_API_KEY` | 無償枠あり（要登録）。国連データ利用ポリシーに従い出典明記 |
| 米国EIA | `eia_fetcher` | `EIA_API_KEY` | 米政府作成部分はパブリックドメイン。出典明記を推奨 |
| USGS 地震カタログ | `usgs_fetcher` | 不要 | 米政府パブリックドメイン。出典明記を推奨 |
| USDA NASS QuickStats | `usda_fetcher` | `USDA_API_KEY` | 米政府データ。出典明記を推奨 |
| FAOSTAT | `usda_fetcher` | 不要 | FAOのオープンデータライセンス（CC BY 4.0 系）。出典明記【規約原文は要確認】 |
| NASA FIRMS | `firms_fetcher` | `NASA_FIRMS_API_KEY` | MAP KEY取得（無償）。NASA FIRMS/LANCE のデータ利用表記を推奨（"We acknowledge the use of data from NASA FIRMS"） |
| ENTSO-E Transparency Platform | `entsoe_fetcher` | `ENTSOE_API_KEY` | 要登録（セキュリティトークン）。出典明記 |
| ECB Data Portal（為替） | `official_fx_fetcher` | 不要 | 出典明記。レートは「参考レート」であり取引用途を想定しない |
| GDELT | `gdelt_fetcher` | 不要 | オープンデータ。出典明記を推奨 |
| Nager.Date（世界の祝日） | `events_fetcher` | 不要 | OSSプロジェクト（MIT）の無償API |

### 民間サービス・非公式API

| ソース | フェッチャー | キー | 利用条件の要点 |
|---|---|---|---|
| Yahoo Finance (yfinance) | `yahoo_fetcher` / `freight_fetcher` | 不要 | ⚠️ **非公式ライブラリ**。Yahoo!の利用規約上グレーであり、個人利用・研究用途に留めることを推奨。商用プロダクトへの組み込みは非推奨。予告なく取得不能になるリスクあり |
| Google Trends (pytrends) | `trends_fetcher` | 不要 | ⚠️ **非公式ライブラリ**。Google の利用規約上グレー。レート制限あり。同上のリスク |
| YouTube Data API v3 | `youtube_fetcher` | `YOUTUBE_API_KEY` | 公式API。**YouTube API Services Terms of Service の遵守が必須**（データの保存期間制限等あり） |
| xAI Grok API | `x_grok_fetcher` | `XAI_API_KEY` | **有償API**。xAI利用規約に従う。X（Twitter）投稿の再配布・保存には Xのコンテンツ利用条件が別途適用される点に注意 |
| Datalastic（AIS船舶） | `ais_fetcher` | `DATALASTIC_API_KEY` | **商用有償API**。契約条件に従う |
| AISHub（AIS船舶） | `ais_fetcher` | `AISHUB_USERNAME` | AISデータを相互提供するメンバーのみ利用可 |
| zipcloud 郵便番号API | `zipcode_fetcher` | 不要 | アイビス社提供の無償API。利用規約に従う（元データは日本郵便の郵便番号データ＝自由利用可） |

---

## 3. 免責事項

- 本ドキュメントは 2026-07-08 時点の各規約の要点を開発者がまとめたものであり、法的助言ではありません。
- 各サービスの規約・提供状況は予告なく変更されます。**本スキルの利用者は、自身の利用形態（特に商用利用・データ再配布）が各提供元の規約に適合することを自ら確認する責任を負います。**
- 非公式API（yfinance / pytrends）に依存する機能は、提供元の仕様変更により突然動作しなくなる可能性があります。
