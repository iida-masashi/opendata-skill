import argparse
from datetime import datetime

import polars as pl
import requests  # noqa: F401 - テストが events_fetcher.requests.get を patch する
from dotenv import load_dotenv

from api_utils import cli_entry, save_output
from api_utils import get_with_retry as _get_with_retry

load_dotenv()


def fetch_events_data(year: int, country_code: str = "JP", output_file: str | None = None) -> pl.DataFrame:  # noqa: E501
    """
    局所的イベント・カレンダー要因（祝日など）を取得するわ。
    まずは無料の Nager.Date API を使って祝日特需フラグを生成するわよ。
    """
    url = f"https://date.nager.at/api/v3/PublicHolidays/{year}/{country_code}"

    print(f"Fetching Event/Holiday data for {country_code} in {year}...")
    response = _get_with_retry(url)
    holidays = response.json()

    if not holidays:
        print("No holiday data found.")
        return pl.DataFrame()

    # データ整形
    records = []
    for h in holidays:
        records.append({
            "date": h["date"],
            "event_name": h["localName"],
            "is_holiday": 1,
            "event_type": "Public Holiday"
        })

    df = pl.DataFrame(records)
    save_output(df, output_file)
    return df

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch local events and holidays.")
    parser.add_argument("--year", type=int, default=datetime.now().year, help="Year to fetch events for.")  # noqa: DTZ005, E501
    parser.add_argument("--country", default="JP", help="Country code (e.g., JP, US).")
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    fetch_events_data(args.year, args.country, args.out)

if __name__ == "__main__":
    cli_entry(main)
