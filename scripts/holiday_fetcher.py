import argparse

import polars as pl
import requests


def fetch_japan_holidays(output_file: str | None = None) -> None:
    """
    Fetches Japanese Public Holidays from Cabinet Office (Cao) CSV.
    URL: https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv
    """
    url = "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv"

    print("Fetching Japanese Holidays from Cabinet Office...")

    try:
        response = requests.get(url)  # noqa: S113
        response.raise_for_status()
        # Encoding is Shift-JIS
        csv_data = response.content.decode('shift_jis')
    except Exception as e:  # noqa: BLE001
        print(f"Error fetching holidays: {e}")
        return

    # Parse
    try:
        df = pl.read_csv(csv_data.encode('utf-8'))
    except Exception as e:  # noqa: BLE001
        print(f"Error parsing CSV: {e}")
        return

    # Standardize columns
    # Usually: "国民の祝日・休日月日", "国民の祝日・休日名称"
    df.columns = ["Date", "Name"]

    # Sort
    df = df.with_columns(pl.col("Date").str.to_date("%Y/%m/%d"))
    df = df.sort("Date")

    if not output_file:
        output_file = "japan_holidays.csv"

    print(f"Saving {len(df)} holidays to {output_file}...")
    df.write_csv(output_file, include_header=True)
    print("Done.")

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Japanese Public Holidays.")
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    fetch_japan_holidays(args.out)

if __name__ == "__main__":
    main()
