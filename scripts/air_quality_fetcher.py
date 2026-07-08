import argparse
from typing import Any

import polars as pl
import requests

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


def fetch_air_quality(
    lat: float,
    lon: float,
    output_file: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """
    Fetches Air Quality data from Open-Meteo API.
    Replaces "AEROS" which has no public API.
    """
    base_url = "https://air-quality-api.open-meteo.com/v1/air-quality"

    params: dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone,dust",
    }

    if start_date and end_date:
        params["start_date"] = start_date
        params["end_date"] = end_date

    print(f"Fetching Air Quality (Lat: {lat}, Lon: {lon})...")

    try:
        response = _get_with_retry(base_url, params=params, timeout=30)
        data = response.json()
    except Exception as e:
        print(f"Error fetching Air Quality data: {e}")
        return

    hourly_data = data.get("hourly", {})
    if not hourly_data:
        print("No data found.")
        return

    df = pl.DataFrame(hourly_data)

    if not output_file:
        output_file = f"air_quality_{lat}_{lon}.csv"

    print(f"Saving to {output_file}...")
    df.write_csv(output_file, include_header=True)
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Air Quality (Open-Meteo).")
    parser.add_argument("--lat", required=True, type=float, help="Latitude")
    parser.add_argument("--lon", required=True, type=float, help="Longitude")
    parser.add_argument("--start", help="Start Date (YYYY-MM-DD)")
    parser.add_argument("--end", help="End Date (YYYY-MM-DD)")
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    fetch_air_quality(args.lat, args.lon, args.out, args.start, args.end)
