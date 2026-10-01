import argparse
from typing import Any

import polars as pl
import requests  # noqa: F401 - テストが air_quality_fetcher.requests.get を patch する
from api_utils import cli_entry, save_output
from meteo_fetcher import apply_date_range, request_open_meteo


def fetch_air_quality(
    lat: float,
    lon: float,
    output_file: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """
    Fetches Air Quality data from Open-Meteo API.
    Replaces "AEROS" which has no public API.
    start_date / end_date は両方指定するか両方省略する。
    """
    base_url = "https://air-quality-api.open-meteo.com/v1/air-quality"

    params: dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone,dust",
    }

    apply_date_range(params, start_date, end_date)

    print(f"Fetching Air Quality (Lat: {lat}, Lon: {lon})...")

    data = request_open_meteo(base_url, params, timeout=30)

    if "hourly" not in data:
        raise RuntimeError(f"Open-Meteo Air Quality response has no 'hourly' data (keys: {sorted(data)})")

    df = pl.DataFrame(data["hourly"])

    save_output(df, output_file)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Air Quality (Open-Meteo).")
    parser.add_argument("--lat", required=True, type=float, help="Latitude")
    parser.add_argument("--lon", required=True, type=float, help="Longitude")
    parser.add_argument("--start", help="Start Date (YYYY-MM-DD). Use together with --end")
    parser.add_argument("--end", help="End Date (YYYY-MM-DD). Use together with --start")
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    output_file = args.out or f"air_quality_{args.lat}_{args.lon}.csv"
    fetch_air_quality(args.lat, args.lon, output_file, args.start, args.end)


if __name__ == "__main__":
    cli_entry(main)
