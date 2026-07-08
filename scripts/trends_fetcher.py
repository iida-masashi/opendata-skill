import argparse

import polars as pl
from pytrends.request import TrendReq


def fetch_google_trends(
    keywords: str | list[str],
    timeframe: str = "today 5-y",
    geo: str = "JP",
    output_file: str | None = None,
) -> None:
    """
    Fetches Google Trends data.
    """

    # Process keywords
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(',')]

    print(f"Fetching Google Trends for: {keywords} (Geo: {geo}, Timeframe: {timeframe})...")  # noqa: E501

    try:
        # retries/backoff_factor は pytrends 内蔵のリトライ。429 Too Many Requests を
        # 指数バックオフで自動再試行させる (Google Trends 非公式APIは429が頻発)。
        pytrends = TrendReq(hl='ja-JP', tz=540, retries=3, backoff_factor=2) # Japan timezone
        pytrends.build_payload(keywords, cat=0, timeframe=timeframe, geo=geo, gprop='')

        df = pytrends.interest_over_time()

    except Exception as e:  # noqa: BLE001
        print(f"Error fetching Google Trends: {e}")
        print("Note: Google Trends API (unofficial) often returns 429 Too Many Requests.")  # noqa: E501
        return

    if df.empty:
        print("No data found.")
        return

    # Drop 'isPartial' column if exists
    if 'isPartial' in df.columns:
        df = df.drop(columns=['isPartial'])

    # Reset index to include 'date' in CSV
    df.reset_index(inplace=True)
    df_polars = pl.from_pandas(df)

    # Output filename
    if not output_file:
        kw_str = "_".join(keywords[:2])
        output_file = f"trends_{kw_str}.csv"

    print(f"Saving to {output_file}...")
    try:
        df_polars.write_csv(output_file, include_header=True)
    except Exception as e:  # noqa: BLE001
        print(f"Error saving CSV: {e}")

    print("Done.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Google Trends Data.")
    parser.add_argument("--keywords", required=True, help="Keywords (comma-separated). e.g., 'Python, Java, Rust'")  # noqa: E501
    parser.add_argument("--geo", default="JP", help="Geo Code (e.g., 'JP', 'US', 'world'). Default: 'JP'")  # noqa: E501
    parser.add_argument("--timeframe", default="today 5-y", help="Timeframe (e.g., 'today 12-m', 'today 5-y', '2020-01-01 2023-12-31'). Default: 'today 5-y'")  # noqa: E501
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    fetch_google_trends(args.keywords, args.timeframe, args.geo, args.out)
