import argparse

import polars as pl
import requests  # noqa: F401 - テストが river_fetcher.requests.get を patch する

from api_utils import cli_entry, save_output
from api_utils import get_with_retry as _get_with_retry


def fetch_river_discharge(
    lat: float,
    lon: float,
    output_file: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """
    Fetches River Discharge data from Open-Meteo Flood API.
    """
    base_url = "https://flood-api.open-meteo.com/v1/flood"

    params: dict[str, str | float] = {
        "latitude": lat,
        "longitude": lon,
        "daily": "river_discharge"
    }

    # 片方だけ指定すると黙って無視され既定期間が返っていたため、明示的に弾く。
    if bool(start_date) != bool(end_date):
        raise ValueError("start_date と end_date は両方指定するか、両方省略してください。")
    if start_date and end_date:
        params["start_date"] = start_date
        params["end_date"] = end_date

    print(f"Fetching River Discharge (Lat: {lat}, Lon: {lon})...")

    response = _get_with_retry(base_url, params=params)
    data = response.json()

    daily_data = data.get('daily', {})
    if not daily_data:
        print("No river discharge data found nearby.")
        return pl.DataFrame()

    df = pl.DataFrame(daily_data)
    save_output(df, output_file)
    return df

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch River Discharge (Open-Meteo Flood API).")  # noqa: E501
    parser.add_argument("--lat", required=True, type=float, help="Latitude")
    parser.add_argument("--lon", required=True, type=float, help="Longitude")
    parser.add_argument("--start", help="Start Date (YYYY-MM-DD)")
    parser.add_argument("--end", help="End Date (YYYY-MM-DD)")
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    output_file = args.out or f"river_discharge_{args.lat}_{args.lon}.csv"
    fetch_river_discharge(args.lat, args.lon, output_file, args.start, args.end)

if __name__ == "__main__":
    cli_entry(main)
