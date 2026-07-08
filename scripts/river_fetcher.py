import argparse

import polars as pl
import requests


def fetch_river_discharge(
    lat: float,
    lon: float,
    output_file: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """
    Fetches River Discharge data from Open-Meteo Flood API.
    """
    base_url = "https://flood-api.open-meteo.com/v1/flood"

    params: dict[str, str | float] = {
        "latitude": lat,
        "longitude": lon,
        "daily": "river_discharge"
    }

    if start_date and end_date:
        params["start_date"] = start_date
        params["end_date"] = end_date

    print(f"Fetching River Discharge (Lat: {lat}, Lon: {lon})...")

    try:
        response = requests.get(base_url, params=params)  # noqa: S113
        response.raise_for_status()
        data = response.json()
    except Exception as e:  # noqa: BLE001
        print(f"Error fetching River data: {e}")
        return

    daily_data = data.get('daily', {})
    if not daily_data:
        print("No river discharge data found nearby.")
        return

    df = pl.DataFrame(daily_data)

    if not output_file:
        output_file = f"river_discharge_{lat}_{lon}.csv"

    print(f"Saving to {output_file}...")
    df.write_csv(output_file, include_header=True)
    print("Done.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch River Discharge (Open-Meteo Flood API).")  # noqa: E501
    parser.add_argument("--lat", required=True, type=float, help="Latitude")
    parser.add_argument("--lon", required=True, type=float, help="Longitude")
    parser.add_argument("--start", help="Start Date (YYYY-MM-DD)")
    parser.add_argument("--end", help="End Date (YYYY-MM-DD)")
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    fetch_river_discharge(args.lat, args.lon, args.out, args.start, args.end)
