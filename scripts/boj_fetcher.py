"""日本銀行 時系列統計データ検索 API フェッチャー (短観 TANKAN 等)。

BOJ Time-Series Data Search の公開REST API (APIキー不要)。
短観の業況判断DIなど、SCM需要予測の先行指標として有用な企業景況感を取得する。

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

# よく使う短観シリーズのエイリアス → BOJ系列コード (API用の bare TK 形式)。
# DI: 業況判断 (「良い」-「悪い」)。最近=…01000 / 先行き=…11000。
# 期 (SURVEY_DATES YYYYQQ) は暦ベース: 01=3月調査, 02=6月, 03=9月, 04=12月。
SERIES_ALIAS = {
    "tankan_large_mfg": "TK99F1000601GCQ01000",        # 大企業・製造業 業況判断DI(最近)
    "tankan_large_mfg_fc": "TK99F1000601GCQ11000",     # 大企業・製造業 業況判断DI(先行き)
    "tankan_large_all": "TK99F0000601GCQ01000",        # 大企業・全産業 業況判断DI(最近)
    "tankan_mid_mfg": "TK99F1000601GCQ02000",          # 中堅・製造業 業況判断DI(最近)
    "tankan_small_mfg": "TK99F1000601GCQ03000",        # 中小・製造業 業況判断DI(最近)
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
    db: str = "CO",
    lang: str = "en",
    output_file: str | None = None,
) -> pl.DataFrame:
    """BOJ 時系列APIから系列データを取得する。

    - series: SERIES_ALIAS のキー、または BOJ系列コード (TK… 形式) を直接指定。
    - start_date/end_date: YYYYMM 形式 (任意)。
    戻り値は date(=SURVEY_DATES) / value(=VALUES) を含む正規化済み DataFrame。
    """
    code = SERIES_ALIAS.get(series, series)

    params: dict[str, Any] = {"format": "csv", "lang": lang, "db": db, "code": code}
    if start_date:
        params["startDate"] = start_date
    if end_date:
        params["endDate"] = end_date

    print(f"Fetching BOJ series {code} (db={db})...")
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
    parser = argparse.ArgumentParser(description="Fetch BOJ Time-Series data (TANKAN etc.).")
    parser.add_argument(
        "--series", default="tankan_large_mfg",
        help=f"Alias {list(SERIES_ALIAS.keys())} or a raw BOJ series code (TK...).",
    )
    parser.add_argument("--start", help="Start period (YYYYMM).")
    parser.add_argument("--end", help="End period (YYYYMM).")
    parser.add_argument("--out", help="Output CSV filename.")
    args = parser.parse_args()
    fetch_boj_data(
        series=args.series, start_date=args.start, end_date=args.end, output_file=args.out
    )


if __name__ == "__main__":
    cli_entry(main)
