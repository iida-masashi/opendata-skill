"""日本銀行 時系列統計データ検索 API フェッチャー (短観 TANKAN 等)。

BOJ Time-Series Data Search の公開REST API (APIキー不要)。
短観の業況判断DIなど、SCM需要予測の先行指標として有用な企業景況感を取得する。

エンドポイント: https://www.stat-search.boj.or.jp/api/v1/getDataCode
レスポンスCSVは STATUS/NEXTPOSITION 等のメタ前文の後に SERIES_CODE 始まりの
本体ヘッダが続くため、本体ヘッダ行までスキップしてからパースする。
"""
import argparse
import io
from typing import Any

import polars as pl
import requests

try:
    from api_utils import retry_with_ratelimit
except ImportError:
    from .api_utils import retry_with_ratelimit

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


@retry_with_ratelimit
def _get_with_retry(url: str, **kwargs: Any) -> requests.Response:
    """BOJ API を呼びつつ 429/5xx で再試行する。"""
    kwargs.setdefault("timeout", 60)
    resp = requests.get(url, **kwargs)
    resp.raise_for_status()
    return resp


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
    try:
        resp = _get_with_retry(API_URL, params=params)
    except Exception as e:  # noqa: BLE001
        print(f"Error fetching BOJ data: {e}")
        return pl.DataFrame()

    # メタ前文をスキップ: 本体ヘッダ ('SERIES_CODE,' で始まる行) を探す。
    lines = resp.text.splitlines()
    header_idx = next(
        (i for i, ln in enumerate(lines) if ln.startswith("SERIES_CODE,")), None
    )
    if header_idx is None or header_idx + 1 >= len(lines):
        print("No BOJ data rows found.")
        return pl.DataFrame()

    body = "\n".join(lines[header_idx:])
    df = pl.read_csv(io.StringIO(body))
    if df.is_empty():
        print("No BOJ data rows found.")
        return pl.DataFrame()

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

    if output_file:
        print(f"Saving to {output_file}...")
        df.write_csv(output_file)
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
    main()
