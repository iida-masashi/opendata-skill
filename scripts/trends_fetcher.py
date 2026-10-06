import argparse
from typing import Any

import polars as pl
from api_utils import cli_entry, save_output
from trendspyg import (
    download_google_trends_comparison,
    download_google_trends_interest_over_time,
)


def _interest_over_time(keywords: list[str], timeframe: str, geo: str) -> list[dict[str, Any]]:
    """[{'date': ISO8601(UTC), 'values': {kw: 0-100}, 'is_partial': bool}, ...] を返す。

    engine="http" は Chrome を起動せず Google に直接問い合わせる（既定の "browser" は Chrome を起動する）。
    trendspyg の http 経路は内部でリトライせず、403/429 で即 RateLimitError を送出し、その後5分間は
    同じプロセスからの要求も即失敗させる。ここで再試行しても無意味なので1回だけ試して例外をそのまま送出する。
    キャッシュは Hub の CacheManager が持つため trendspyg 側の cache/cookies は使わない。
    """
    if len(keywords) == 1:
        points = download_google_trends_interest_over_time(
            keywords[0], geo=geo, timeframe=timeframe, engine="http"
        )
        return [
            {"date": p["date"], "values": {keywords[0]: p["value"]}, "is_partial": p["is_partial"]}
            for p in points
        ]
    # 2〜5 キーワードは同一スケールで比較される（6 以上は trendspyg が InvalidParameterError）
    result = download_google_trends_comparison(
        keywords, geo=geo, timeframe=timeframe, include_geo=False, engine="http"
    )
    return result["interest_over_time"]


def fetch_google_trends(
    keywords: str | list[str],
    timeframe: str = "today 5-y",
    geo: str = "JP",
    output_file: str | None = None,
) -> pl.DataFrame:
    """
    Fetches Google Trends data (trendspyg).
    - geo: 国コード ('JP', 'US', ...)。全世界は '' （'world' も '' として扱う）。
    - is_partial=True の行（集計途中の最新期間）は値が確定していないため落とす。
    - date は UTC の naive datetime（日次以上は日付の 00:00、時間足は UTC 時刻）。
    """

    # Process keywords
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(',')]

    # Google Trends の全世界指定は geo=''（'world' をそのまま送ると国コードとして解釈されない）
    if geo.lower() == "world":
        geo = ""

    print(f"Fetching Google Trends for: {keywords} (Geo: {geo or 'worldwide'}, Timeframe: {timeframe})...")

    points = [p for p in _interest_over_time(keywords, timeframe, geo) if not p["is_partial"]]

    if not points:
        print("No data found.")
        return pl.DataFrame()

    df_polars = pl.DataFrame(
        {"date": [p["date"] for p in points]}
        | {kw: [p["values"][kw] for p in points] for kw in keywords}
    ).with_columns(
        pl.col("date").str.to_datetime(time_zone="UTC").dt.replace_time_zone(None).dt.cast_time_unit("us")
    )

    save_output(df_polars, output_file)
    return df_polars

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Google Trends Data.")
    parser.add_argument("--keywords", required=True, help="Keywords (comma-separated). e.g., 'Python, Java, Rust'")
    parser.add_argument("--geo", default="JP", help="Geo Code (e.g., 'JP', 'US'). Use '' or 'world' for worldwide. Default: 'JP'")
    parser.add_argument("--timeframe", default="today 5-y", help="Timeframe (e.g., 'today 12-m', 'today 5-y', '2020-01-01 2023-12-31'). Default: 'today 5-y'")
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    output_file = args.out
    if not output_file:
        kw_str = "_".join(k.strip() for k in args.keywords.split(',')[:2])
        output_file = f"trends_{kw_str}.csv"
    fetch_google_trends(args.keywords, args.timeframe, args.geo, output_file)

if __name__ == "__main__":
    cli_entry(main)
