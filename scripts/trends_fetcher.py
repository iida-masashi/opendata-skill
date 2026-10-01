import argparse

import polars as pl
from api_utils import cli_entry, save_output
from pytrends.request import TrendReq


def fetch_google_trends(
    keywords: str | list[str],
    timeframe: str = "today 5-y",
    geo: str = "JP",
    output_file: str | None = None,
) -> pl.DataFrame:
    """
    Fetches Google Trends data.
    - geo: 国コード ('JP', 'US', ...)。全世界は '' （'world' も '' として扱う）。
    - isPartial=True の行（集計途中の最新期間）は値が確定していないため落とす。
    """

    # Process keywords
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(',')]

    # pytrends の全世界指定は geo=''（'world' をそのまま送ると Google 側で国コードとして解釈されない）
    if geo.lower() == "world":
        geo = ""

    print(f"Fetching Google Trends for: {keywords} (Geo: {geo or 'worldwide'}, Timeframe: {timeframe})...")

    # retries/backoff_factor は pytrends 内蔵のリトライ。429 Too Many Requests を
    # 指数バックオフで自動再試行させる (Google Trends 非公式APIは429が頻発)。
    pytrends = TrendReq(hl='ja-JP', tz=540, retries=3, backoff_factor=2) # Japan timezone
    pytrends.build_payload(keywords, cat=0, timeframe=timeframe, geo=geo, gprop='')

    df = pytrends.interest_over_time()

    if df.empty:
        print("No data found.")
        return pl.DataFrame()

    # 不完全期間の行を落としてから 'isPartial' 列を削除
    if 'isPartial' in df.columns:
        df = df[~df['isPartial'].astype(bool)]
        df = df.drop(columns=['isPartial'])

    # Reset index to include 'date'
    df_polars = pl.from_pandas(df.reset_index())

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
