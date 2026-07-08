import argparse
import datetime

import polars as pl
import requests


def fetch_power_usage(
    area: str = "tokyo", date: str | None = None, output_file: str | None = None
) -> None:
    """
    Fetches electric power usage and supply/demand data.
    """

    # Map areas to endpoints (TEPCO example)
    # Note: Each power company has different URL structures.
    # We will focus on TEPCO for this MVP.

    if area.lower() != "tokyo":
        print("Sorry, currently only 'tokyo' (TEPCO) is supported in this MVP script.")
        print("Please check other power companies' websites for their CSV URLs.")
        return

    # Try current year, then previous year
    current_year = datetime.datetime.now().year  # noqa: DTZ005
    years_to_try = [current_year, current_year - 1]

    response = None
    target_year = current_year

    for year in years_to_try:
        url = f"https://www.tepco.co.jp/forecast/html/images/juyo-{year}.csv"
        print(f"Trying URL: {url}...")
        try:
            r = requests.get(url)  # noqa: S113
            if r.status_code == 200:  # noqa: PLR2004
                response = r
                target_year = year  # noqa: F841
                break
        except Exception:  # noqa: BLE001, S112
            continue

    used_daily_fallback = False
    if not response:
        # Final fallback to known daily URL pattern or error
        print("Yearly CSVs not found. Trying daily latest...")
        url = "https://www.tepco.co.jp/forecast/html/images/juyo-d-j.csv"
        try:
            r = requests.get(url)  # noqa: S113
            if r.status_code == 200:  # noqa: PLR2004
                response = r
                used_daily_fallback = True
            else:
                print("Could not find any valid TEPCO CSV URL.")
                return
        except Exception as e:  # noqa: BLE001
            print(f"Error: {e}")
            return

    # Process response
    try:
        # TEPCO CSV encoding is Shift-JIS
        csv_data = response.content.decode('shift_jis', errors='replace')
    except Exception as e:  # noqa: BLE001
        print(f"Error decoding: {e}")
        return

    # Parse CSV
    # TEPCO CSV structure: DATE, TIME, USAGE(10MW)... headers are in Japanese.
    # Usually skip first few lines of metadata.

    # Find the header line. Usually "DATE,TIME,実績(万kW)"
    # Let's try reading with polars skipping rows until header.

    try:
        # TEPCO CSV format varies slightly by year but usually header is around line 1 or 2  # noqa: E501
        df = pl.read_csv(csv_data.encode('utf-8'), skip_rows=1) # Often row 0 is title, row 1 is header  # noqa: E501

        # Check columns
        # Expected: DATE, TIME, ...
        # If columns look wrong, try skipping more/less.

    except Exception as e:  # noqa: BLE001
        print(f"Error parsing CSV: {e}")
        return

    # Filter by date if specified
    if date:
        # TEPCO date format is usually YYYY/M/D
        # Normalize date column
        # Assuming first column is DATE
        date_col = df.columns[0]
        # Convert to datetime to filter
        df = df.with_columns(pl.col(date_col).str.to_date("%Y/%m/%d"))

        target_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        df = df.filter(pl.col(date_col) == target_date)

        if df.is_empty():
            print(f"No data found for date: {date}")
            return

    # Output filename. The daily-latest fallback is not a full year's data, so
    # don't mislabel it with target_year.
    if not output_file:
        suffix = "daily_latest" if used_daily_fallback else str(target_year)
        output_file = f"power_{area}_{suffix}.csv"

    print(f"Saving to {output_file}...")
    df.write_csv(output_file, include_header=True)
    print("Done.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Electric Power Usage (TEPCO).")
    parser.add_argument("--area", default="tokyo", help="Power Area (currently only 'tokyo' supported)")  # noqa: E501
    parser.add_argument("--date", help="Specific Date (YYYY-MM-DD). If omitted, fetches full year data.")  # noqa: E501
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    fetch_power_usage(args.area, args.date, args.out)
