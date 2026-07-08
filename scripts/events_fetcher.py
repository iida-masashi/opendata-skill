import argparse
from datetime import datetime
from typing import Any

import polars as pl
import requests
from dotenv import load_dotenv

load_dotenv()

try:
    from api_utils import retry_with_ratelimit
except ImportError:
    from .api_utils import retry_with_ratelimit


@retry_with_ratelimit
def _get_with_retry(url: str, **kwargs: Any) -> requests.Response:
    """module の requests.get を呼びつつ 429/5xx で再試行する（テストは patch 可能なまま）。"""
    kwargs.setdefault("timeout", 60)
    resp = requests.get(url, **kwargs)
    resp.raise_for_status()
    return resp

def fetch_events_data(year: int, country_code: str = "JP", output_file: str | None = None) -> pl.DataFrame:  # noqa: E501
    """
    局所的イベント・カレンダー要因（祝日など）を取得するわ。
    まずは無料の Nager.Date API を使って祝日特需フラグを生成するわよ。
    """
    url = f"https://date.nager.at/api/v3/PublicHolidays/{year}/{country_code}"

    print(f"Fetching Event/Holiday data for {country_code} in {year}...")
    try:
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

        if output_file:
            print(f"Saving to {output_file}...")
            df.write_csv(output_file)

        return df  # noqa: TRY300

    except Exception as e:  # noqa: BLE001
        print(f"Error fetching event data: {e}")
        return pl.DataFrame()

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch local events and holidays.")
    parser.add_argument("--year", type=int, default=datetime.now().year, help="Year to fetch events for.")  # noqa: DTZ005, E501
    parser.add_argument("--country", default="JP", help="Country code (e.g., JP, US).")
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    fetch_events_data(args.year, args.country, args.out)

if __name__ == "__main__":
    main()
