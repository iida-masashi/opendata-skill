# opendata-skill リファクタリングプラン

確度の凡例:

- **[実行]**: 実際に動かして再現済み
- **[コード]**: 該当コードを読んで確認済み
- **[未検証]**: 指摘のみ。着手前に再現テストで確認する

## 最優先の3件

1. **`require_api_key` と e-Stat フェッチャーが `sys.exit` を呼ぶ [実行]**
   - 該当箇所: `api_utils.py:26`、`estat_fetcher.py:45/49/58/91`
   - `SystemExit` は `get_many` の `except Exception` では捕まらない。キーが1つ未設定なだけで並列バッチ全体が落ち、ライブラリ利用時は呼び出し元のプロセスも終了する。
   - データ0件で `sys.exit(0)` を呼ぶため、失敗が「成功」に見える。
2. **リポジトリ直下から `from scripts.opendata_hub import OpenDataHub` で使うと、フェッチャーを読み込めない [実行]**
   - エラー: `ImportError: attempted relative import with no known parent package`
   - テストは各ファイルが `scripts/` を `sys.path` に入れ、Hub のテストは `_load_module` を差し替えているため、表に出ない。
3. **Hub 経由ではレート制限が効かない [実行]**
   - `_load_module` が毎回モジュールを読み直すため、`rate_limited` の状態（直前の呼び出し時刻）が毎回リセットされる。
   - `rate_limited` にはロックがなく、並列実行では待機が入らない。

## 現状の主な問題

### A. 失敗が「データ無し」に化ける（設計原則「握り潰さない」への違反）

| 内容 | 主な箇所 | 確度 |
|---|---|---|
| `except Exception` で空DF / None を返す | eia, entsoe, gdelt, usgs, firms, usda, boj, comtrade, official_fx, fred, worldbank, yahoo, freight, events, meteo, air_quality, trends, CLI専用フェッチャー13本 | eia / events / official_fx は [コード]、他は [未検証] |
| `e.response.text if e.response else ...` という書き方（4xx/5xx の応答はブール値で False になり、API のエラー本文が表示されない） | 約12ファイル | [コード] |
| e-Stat のリトライが働かない（`RequestException` を捕まえて `sys.exit` するため、tenacity まで届かない） | `estat_fetcher.py:39-45` | [コード] |
| リトライもタイムアウトもない `requests.get` | fred, comtrade, eia, entsoe, ais, power, resas ほか | [未検証] |
| HTTP 200 で返る API エラーを検出していない | BOJ(STATUS), RESAS, AISHub, mlit, zipcode | [未検証] |
| CacheManager がスレッド非対応。並列実行で `metadata` の JSON が壊れることがあり、壊れても `{}` として読み込まれるためキャッシュ全体が気付かれずに消える | `cache_manager.py:80,34` | [コード] |
| `time_align` で `filter_col` が存在しないとき、フィルタを黙って飛ばす | `time_align.py:48` | [未検証] |

### B. データが黙って間違う

| 内容 | 確度 |
|---|---|
| AIS: 登録されていない港を指定すると、AISHub のフォールバックが `bbox=None`（範囲指定なし）になり、全世界の船舶数を「その港の数」として返す | [コード] |
| ENTSO-E: 電源種別（psrType）を落としているため、発電量の全電源が1つの `value` 列に混ざる | [コード] |
| ENTSO-E: Period を最初の1つしか読まない | [コード]（Period が複数ある応答が実在するかは [未検証]） |
| `get_official_fx(source="boj")`: 既定の通貨が JPY のため必ず ValueError になり、握り潰されて空DFになる | [コード] |
| edinet: データ0件のとき改行だけの CSV を書き、Hub 側で NoDataError になる | [コード] |
| meteo: `daily=True` を指定しても日次データが捨てられる | [未検証] |
| yahoo: 日中足（1h など）では `Datetime` 列の名前変更に失敗し、握り潰されて None になる | [未検証] |
| correlation_analyzer: 結合で `value` 列の名前が衝突し、同じ列同士の相関（r=1.0）を計算する | [未検証] |
| feature_engineer: 1行でも解析できた日付フォーマットを採用するため、解析できなかった日付が null になり補間される | [未検証] |
| `pl.DataFrame(records)` が先頭100行にないキーを捨てる（odpt, corp, mlit, x_grok） | [未検証] |

次の7件は不確実性が高い。修正前に一次情報で確認する。

- Comtrade の台湾コード `TW=158`
- BOJ のページング（NEXTPOSITION）
- x_grok が投稿を捏造する可能性
- power の CSV レイアウト
- pmi のエイリアス（NAPM が廃止系列であることなど）
- plateau が検索結果の1件目を無条件に採用する件
- corp が分割結果の1ページ目しか取らない件

### C. 重複コード

| 重複 | 箇所 | 共通化先 |
|---|---|---|
| `_get_with_retry` の完全コピー | 8ファイル | `api_utils` に1つ |
| HTTPError を処理する末尾ブロック（`e.response` バグごと複製） | 約12ファイル | `format_http_error()` |
| 「既定の期間＝今日からN日前まで」の計算（UTC と naive の時刻が混在） | eia, entsoe, usgs, gdelt, fred, yahoo, freight, official_fx | `default_date_range()` |
| CSV 保存の定型処理（"Saving…" → `write_csv` → "Done."） | 約20ファイル | `save_output()` |
| FRED のエイリアス取得 | `pmi:46-62` と `semicon:44-60` がほぼ同一 | fred_fetcher に `fetch_fred_alias()` |
| yfinance の取得と MultiIndex の平坦化 | yahoo と freight で別々に実装 | freight を yahoo の呼び出しに変える |
| Hub の旧 `get_*` 8本（weather〜estat）が `_cached_fetch` の中身を手で書いている | `opendata_hub.py:76-246` | `_cached_fetch` に統一 |
| 日付フォーマット一覧が2か所にあり、使い方も異なる | `feature_engineer.py:6` と `time_align.py:61` | 1か所に集約 |
| テストの `sys.path.insert` / モック応答 / `hub` フィクスチャ | テストファイル約26本 | `conftest.py` |

`patch("<module>.requests.get")` は `requests` モジュールそのものの `get` を差し替えるので、別モジュールに置いた共有ヘルパーにも効く [実行]。`_get_with_retry` はテストの書き方を変えずに共通化できる。CLAUDE.md の「モジュールごとに置く」という規約の記述もあわせて直す。

### D. テスト

- 実ネットワークにアクセスするテストが、通常の `pytest` 実行で走る（usgs, official_fx, gdelt, usda）。アサーションが緩く、API が壊れていても通る。
- 「失敗しても空で返る」挙動を正しいものとして固定しているテストがある（meteo, zipcode, ckan, trends, yahoo, official_fx）。
- テストが `os.environ` に入れたダミーの API キーを元に戻していない（eia, pmi, semicon, usda）。
- テストがないフェッチャーが14本ある（air_quality, edinet, events, gsi, holiday, maff, mlit, plateau, power, resas, river, trade, x_grok, youtube）。

## 実施フェーズ

各項目は「再現テストを先に書いて失敗を確認する → 修正 → 成功を確認」の順で進める。

### Phase 0: テスト基盤を先に固める

- `conftest.py` を作り、`hub` フィクスチャ、モック応答、`monkeypatch.setenv` を共通化する。
- `integration` マーカーを登録し、実ネットワークのテストは通常実行から外す。
- **注意:** pytest 設定で `pythonpath=["scripts"]` を一律に足すと、最優先2の import 不具合が永久に隠れる。代わりに、`sys.path` に何も足さないサブプロセスから実際の `_load_module` で全フェッチャーを読み込む回帰テストを追加する。

### Phase 1: Hub 中核（最優先の3件と、並列実行時の安全性）

1. `MissingApiKeyError` を新設し、ライブラリ内の `sys.exit` を例外の送出に置き換える。終了コードへの変換は各 `main()` だけで行う。
2. `_load_module` で読み込んだモジュールをキャッシュし、`scripts/` を `sys.path` に解決できるようにする。
3. `rate_limited` にロックを付け、呼び出し前に実行枠を確保する方式にする。
4. `get_many` が `(results, errors)` 相当の形でエラーも返すようにし、失敗と0件を区別できるようにする。
5. CacheManager にロックを付け、書き込みを「一時ファイルに書いてから `os.replace` で置き換える」方式にする。
6. `api_utils.py:57` で、`urllib.error.HTTPError`（`URLError` のサブクラス）の 4xx がリトライ対象になる潜在バグを直す。

### Phase 2: 共通ヘルパーの導入（C の表のとおり）

- `api_utils` に `get_with_retry`、`format_http_error`、`default_date_range`、`save_output` を置く。
- Hub の旧 `get_*` 8本を `_cached_fetch` に統一する。キャッシュのキー名は変えず、既存キャッシュを無効化しない。
- argparse の定型処理は効果が小さいので、共通化しない。

### Phase 3: 握り潰しの除去（Hub から呼ばれる経路を優先）

- 対象（Hub 経由）: estat, fred（pmi / semicon 含む）, worldbank, yahoo, freight, oecd, trends, meteo, eia, entsoe, gdelt, ais, usda, usgs, firms, official_fx, boj, comtrade, edinet
- 除去と同じコミットで、握り潰しを固定しているテストを書き換える。別のコミットにするとテストが赤くなる。
- 各 `main()` は例外を受けて0以外の終了コードで終わるようにする。`examples/all_concurrent_tester.py` は終了コード0だけで合格と判定するため。
- None を返して CSV だけ書いているフェッチャーは、`pl.DataFrame` を返す形に揃える。
- すべての `requests` 呼び出しにタイムアウトを付ける。

### Phase 4: データ破損系の個別バグ（B の表）

- まず [コード] で確認済みのもの（AIS、ENTSO-E、official_fx、edinet）から直す。
- [未検証] の項目は1件ずつ再現テストを書いてから着手する。再現しないものは対象から外す。

### Phase 5: CLI専用フェッチャー13本と整理

- 対象: corp, resas, mlit, plateau, jshis, odpt, gsi, river, zipcode, holiday, ckan, youtube, x_grok
- 握り潰しを除去し、タイムアウトを付ける。
- e-Stat の URL を `http` から `https` にする（現状は appId が平文で送られる）。
- FIRMS の API キーがエラー出力に出るのを伏せる。
- resas / mlit / odpt に `load_dotenv()` を足す。
- maff / trade のプレースホルダは意図的に残してあるが、Hub の自動検出に載る。扱いは別途決める。

## 未決事項

- 旧 `.gemini/skills/opendata-skill` と、スキルとして登録されている `anthropic-skills:opendata-skill` の扱い（廃止するか同期するか）。

## 状況（v2.3.0）

Phase 0〜5 は実施済み。上の A〜D の表の項目は、下の「残課題」に挙げたものを除き対応済み。既定のテスト実行は 368 passed（integration 12件は除外）。

### 対応済みの主な挙動（現在の仕様）

- yahoo: 日次・日中足ともインデックスを `date` 列にする。meteo: `daily=True` で日次を返す。comtrade: 月次の既定 period は YYYYMM
- comtrade: `TW` は理由付きの ValueError（報告国の表に 158 は無く、相手国としての台湾は 490 "Other Asia, nes" に計上される）
- semicon: `us_semi_shipments` は出荷 (A34SVS)、`us_semi_new_orders` は新規受注 (A34SNO)。A34S* は半導体単独でなく「コンピュータ・電子製品」全体
- BOJ: STATUS 前文を検査し、NEXTPOSITION でページングする
- gdelt: 200 + text/html のエラー文は例外にする
- power: タイトル行・空行の後のヘッダ行を探して読む
- corp: 法人名検索は 2,000 件超で分割される仕様に合わせ `divide` でページングする
- plateau: 自治体名で照合し、同名の自治体が複数あれば ValueError
- x_grok: `/v1/responses` + `x_search` ツールで検索し、citation の無い結果は例外にする
- odpt / corp / mlit / x_grok: 全行でスキーマを推論する（`infer_schema_length=None`）
- correlation_analyzer: 結合前に列名を `_1` / `_2` に分ける。feature_engineer / time_align: 全行を1つの形式で解析できる日付だけ採用する
- e-Stat: `DATA_INF.NOTE` の特殊文字（`X`・`-` 等）は `value` を null にし、記号は `value_note` に残す
- RESAS: API が 2025-03-24 に提供終了したため `resas_fetcher` を削除。公式の代替案内に従い、人口構成・事業所数・企業数は e-Stat、不動産取引価格は不動産情報ライブラリ（mlit）
- AIS: `provider='auto'` で Datalastic が失敗したら警告を出して AISHub で取得する（両方失敗なら例外）
- FIRMS: 既定の取得日数は API 仕様（DAY_RANGE 1〜5）に合わせ 5 日

### 残課題

| 内容 | 状態 |
|---|---|
| TEPCO 電力需給 CSV: juyo-2026.csv / juyo-d-j.csv が 404、juyo-2025.csv は 2025-07-22 で停止 | URL 移転の確認が必要 |
| ENTSO-E A75: 揚水等の消費系列（outBiddingZone）が発電系列と同じ psr_type を持つ。curveType A03 で省略された position は欠損のまま | 未対応 |
| PMI: ISM 系列（NAPM 等）は FRED から削除済み。MANEMP / IPMAN は PMI ではない | エイリアスは残し、コメントで実態を明記 |
| FAOSTAT の item に品目名を渡している件 | 一次情報で確認できず保留 |
| e-Stat: NEXT_KEY ページング未対応（10万セル超は切り詰め）、10桁時間コードの解釈 | 未対応 |
| OECD (TIME_PERIOD) / World Bank（ワイド形式 YR*）が Hub の date 契約に乗らない | 未対応 |
| comtrade の `reporter="ALL"` → 0 は報告国として無効 | 未対応 |
| x_grok は実キーで未検証。plateau は同名自治体を区別できない。Datalastic のエラー応答形式は不明 | 未検証 |
| edinet の RateLimitError は日次/月次上限なので、リトライは待ち時間の無駄になりうる | 現状維持 |
| pyarrow が依存に無く、pandas 境界は dict 経由で変換している | 現状維持 |
| maff / trade はプレースホルダのまま Hub の自動検出に載る | 現状維持（案内文のみ修正） |
