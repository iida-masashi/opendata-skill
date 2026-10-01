import argparse

import polars as pl
import requests  # noqa: F401 - テストが holiday_fetcher.requests.get を patch する

from api_utils import cli_entry, save_output
from api_utils import get_with_retry as _get_with_retry


def fetch_japan_holidays(output_file: str | None = None) -> pl.DataFrame:
    """
    Fetches Japanese Public Holidays from Cabinet Office (Cao) CSV.
    URL: https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv
    """
    url = "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv"

    print("Fetching Japanese Holidays from Cabinet Office...")

    response = _get_with_retry(url)
    # Encoding is Shift-JIS
    csv_data = response.content.decode('shift_jis')

    # Parse
    df = pl.read_csv(csv_data.encode('utf-8'))

    # Standardize columns
    # Usually: "国民の祝日・休日月日", "国民の祝日・休日名称"
    df.columns = ["Date", "Name"]

    # Sort
    df = df.with_columns(pl.col("Date").str.to_date("%Y/%m/%d"))
    df = df.sort("Date")

    save_output(df, output_file)
    return df

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Japanese Public Holidays.")
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    fetch_japan_holidays(args.out or "japan_holidays.csv")

if __name__ == "__main__":
    cli_entry(main)
