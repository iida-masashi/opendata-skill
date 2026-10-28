"""日本銀行 時系列統計データ検索 API フェッチャー (短観 TANKAN・企業物価指数 CGPI・SPPI 等)。

BOJ Time-Series Data Search の公開REST API (APIキー不要)。
短観の業況判断DIや企業物価指数(CGPI)など、SCM需要予測・原価予測の先行指標を取得する。

エンドポイント: https://www.stat-search.boj.or.jp/api/v1/getDataCode
レスポンスCSVは STATUS/NEXTPOSITION 等のメタ前文の後に SERIES_CODE 始まりの
本体ヘッダが続くため、本体ヘッダ行までスキップしてからパースする。

API 機能利用マニュアル (2026-02-18) の仕様:
- STATUS は 200 が正常、400/500/503 はエラー。エラー時は format=csv でも JSON で返る。
- 1リクエストの上限 (250系列 / 60,000データ) を超えると NEXTPOSITION に次回検索開始位置が入り、
  STARTPOSITION に指定して続きを取得する (空なら全件取得済み)。
"""
import argparse
import io
import json
from typing import Any

import polars as pl
import requests
from api_utils import cli_entry, format_http_error, save_output
from api_utils import get_with_retry as _get_with_retry

API_URL = "https://www.stat-search.boj.or.jp/api/v1/getDataCode"

# よく使う短観・物価・マネーストックシリーズのエイリアス → BOJ系列コード
SERIES_ALIAS: dict[str, str] = {
    # 短観 (db=CO): DI 業況判断 (「良い」-「悪い」)。最近=…01000 / 先行き=…11000。
    "tankan_large_mfg": "TK99F1000601GCQ01000",        # 大企業・製造業 業況判断DI(最近)
    "tankan_large_mfg_fc": "TK99F1000601GCQ11000",     # 大企業・製造業 業況判断DI(先行き)
    "tankan_large_nonmfg": "TK99F2000601GCQ01000",     # 大企業・非製造業 業況判断DI(最近)
    "tankan_large_nonmfg_fc": "TK99F2000601GCQ11000",  # 大企業・非製造業 業況判断DI(先行き)
    "tankan_large_all": "TK99F0000601GCQ01000",        # 大企業・全産業 業況判断DI(最近)
    "tankan_mid_mfg": "TK99F1000601GCQ02000",          # 中堅・製造業 業況判断DI(最近)
    "tankan_small_mfg": "TK99F1000601GCQ03000",        # 中小・製造業 業況判断DI(最近)
    # 企業物価指数 CGPI (2020年基準, db=PR01): 原材料・仕入コスト・価格転嫁分析用
    "cgpi_all": "PRCG20_2200000000",                   # 国内企業物価指数 総平均
    "cgpi_export": "PRCG20_2400000000",                # 輸出物価指数 総平均(円ベース)
    "cgpi_import": "PRCG20_2600000000",                # 輸入物価指数 総平均(円ベース)
    # 企業向けサービス価格指数 SPPI (2020年基準, db=PR02): 物流・サービス原価分析用
    "sppi_all": "PRCS20_5200000000",                   # 企業向けサービス価格指数 総平均
    # マネーストック (db=MD02)
    "money_stock_m2": "MAM1NAM2M2MO",                  # マネーストック M2 平残
}

# エイリアスごとのデフォルトDBコード（未登録は "CO"）
SERIES_DB_MAP: dict[str, str] = {
    "cgpi_all": "PR01",
    "cgpi_export": "PR01",
    "cgpi_import": "PR01",
    "sppi_all": "PR02",
    "money_stock_m2": "MD02",
}

# NEXTPOSITION を辿る回数の上限（応答異常で無限ループしないための安全弁）
_MAX_PAGES = 100


def _request_page(params: dict[str, Any]) -> str:
    """1ページ分を取得する。エラー時 BOJ は HTTP 4xx/5xx + JSON 本文を返すので、本文を例外メッセージに含める。"""
    try:
        return _get_with_retry(API_URL, params=dict(params)).text
    except requests.exceptions.HTTPError as e:
        raise requests.exceptions.HTTPError(f"BOJ API {format_http_error(e)}", response=e.response) from e


def _parse_page(text: str) -> tuple[pl.DataFrame, str]:
    """1リクエスト分の応答を (本体DF, NEXTPOSITION) にする。API エラーは RuntimeError。"""
    if text.lstrip().startswith("{"):
        err = json.loads(text)
        raise RuntimeError(
            f"BOJ API error STATUS={err.get('STATUS')} {err.get('MESSAGEID')}: {err.get('MESSAGE')}"
        )

    # メタ前文 (STATUS / MESSAGEID / MESSAGE / PARAMETER / NEXTPOSITION ...) を読み、
    # 本体ヘッダ ('SERIES_CODE,' で始まる行) を探す。
    lines = text.splitlines()
    header_idx = None
    meta: dict[str, str] = {}
    for i, ln in enumerate(lines):
        if ln.startswith("SERIES_CODE,"):
            header_idx = i
            break
        key, _, rest = ln.partition(",")
        meta.setdefault(key, rest.split(",")[0].strip())

    if "STATUS" not in meta:
        raise RuntimeError(f"Unexpected BOJ API response: {text[:200]!r}")
    if meta["STATUS"] != "200":
        raise RuntimeError(
            f"BOJ API error STATUS={meta['STATUS']} {meta.get('MESSAGEID', '')}: {meta.get('MESSAGE', '')}"
        )

    next_pos = meta.get("NEXTPOSITION", "")
    if header_idx is None or header_idx + 1 >= len(lines):
        # STATUS=200 で本体が無い (M181030I: 該当データ無し 等)
        return pl.DataFrame(), next_pos
    body = "\n".join(lines[header_idx:])
    return pl.read_csv(io.StringIO(body)), next_pos


def fetch_boj_data(
    series: str = "tankan_large_mfg",
    start_date: str | None = None,
    end_date: str | None = None,
    db: str | None = None,
    lang: str = "en",
    output_file: str | None = None,
) -> pl.DataFrame:
    """BOJ 時系列APIから系列データを取得する。

    - series: SERIES_ALIAS のキー、または BOJ系列コード (TK… / PR… 形式) を直接指定。
    - start_date/end_date: YYYYMM 形式 (任意)。
    - db: BOJ データベース名 (省略時はエイリアスに応じて自動選択、既定は 'CO')。
    戻り値は date(=SURVEY_DATES) / value(=VALUES) を含む正規化済み DataFrame。
    """
    code = SERIES_ALIAS.get(series, series)
    resolved_db = db if db is not None else SERIES_DB_MAP.get(series, "CO")

    params: dict[str, Any] = {"format": "csv", "lang": lang, "db": resolved_db, "code": code}
    if start_date:
        params["startDate"] = start_date
    if end_date:
        params["endDate"] = end_date

    print(f"Fetching BOJ series {code} (db={resolved_db})...")
    pages: list[pl.DataFrame] = []
    for _ in range(_MAX_PAGES):
        page, next_pos = _parse_page(_request_page(params))
        if not page.is_empty():
            pages.append(page)
        if not next_pos:
            break
        params["startPosition"] = next_pos
    else:
        raise RuntimeError(f"BOJ API paging did not finish within {_MAX_PAGES} requests")

    if not pages:
        print("No BOJ data rows found.")
        return pl.DataFrame()
    df = pl.concat(pages, how="diagonal_relaxed")

    # 標準化: SURVEY_DATES -> date, VALUES -> value
    rename = {}
    if "SURVEY_DATES" in df.columns:
        rename["SURVEY_DATES"] = "date"
    if "VALUES" in df.columns:
        rename["VALUES"] = "value"
    if rename:
        df = df.rename(rename)
    if "date" in df.columns:
        df = df.with_columns(pl.col("date").cast(pl.Utf8))
    if "value" in df.columns:
        df = df.with_columns(pl.col("value").cast(pl.Float64, strict=False))

    save_output(df, output_file)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch BOJ Time-Series data (TANKAN, CGPI, SPPI, etc.).")
    parser.add_argument(
        "--series", default="tankan_large_mfg",
        help=f"Alias {list(SERIES_ALIAS.keys())} or a raw BOJ series code.",
    )
    parser.add_argument("--db", default=None, help="BOJ DB code (auto-detected for aliases; default CO).")
    parser.add_argument("--start", help="Start period (YYYYMM).")
    parser.add_argument("--end", help="End period (YYYYMM).")
    parser.add_argument("--out", help="Output CSV filename.")
    args = parser.parse_args()
    fetch_boj_data(
        series=args.series, db=args.db, start_date=args.start, end_date=args.end, output_file=args.out
    )


if __name__ == "__main__":
    cli_entry(main)
