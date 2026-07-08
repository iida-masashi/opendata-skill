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


def fetch_open_meteo(
    latitude: float,
    longitude: float,
    output_file: str | None = None,
    historical: bool = False,
    hourly: bool = True,
    daily: bool = False,
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """
    Fetches weather data from Open-Meteo API.
    """
    base_url = "https://api.open-meteo.com/v1/forecast"
    if historical:
        base_url = "https://archive-api.open-meteo.com/v1/archive"

    # Default params
    params: dict[str, Any] = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": "auto",
        "current_weather": True
    }

    if start_date and end_date:
        params["start_date"] = start_date
        params["end_date"] = end_date

    # Variables
    hourly_vars = ["temperature_2m", "relative_humidity_2m", "precipitation", "rain", "showers", "snowfall", "weathercode", "cloudcover", "windspeed_10m"]  # noqa: E501
    daily_vars = ["temperature_2m_max", "temperature_2m_min", "precipitation_sum", "rain_sum", "showers_sum", "snowfall_sum", "weathercode", "windspeed_10m_max"]  # noqa: E501

    if hourly:
        params["hourly"] = ",".join(hourly_vars)
    if daily:
        params["daily"] = ",".join(daily_vars)

    print(f"Fetching weather data (Lat: {latitude}, Lon: {longitude})...")
    try:
        response = _get_with_retry(base_url, params=params)
        data = response.json()
    except Exception as e:  # noqa: BLE001
        print(f"Error fetching data: {e}")
        return

    # Process
    if not output_file:
        mode = "historical" if historical else "forecast"
        output_file = f"meteo_{mode}_{latitude}_{longitude}.csv"

    # Convert to DataFrame
    # Open-Meteo returns 'hourly': {'time': [...], 'temp': [...], ...}
    # We need to flatten this.

    dfs = []

    if hourly and 'hourly' in data:
        hourly_data = data['hourly']
        df_hourly = pl.DataFrame(hourly_data)
        df_hourly = df_hourly.with_columns(pl.lit('hourly').alias('type'))
        dfs.append(df_hourly)

    if daily and 'daily' in data:
        daily_data = data['daily']
        df_daily = pl.DataFrame(daily_data)
        df_daily = df_daily.with_columns(pl.lit('daily').alias('type'))
        dfs.append(df_daily)

    if not dfs:
        print("No hourly or daily data returned.")
        return

    # Combine or separate? Usually users want one CSV. But hourly/daily have different shapes.  # noqa: E501
    # Let's prioritize hourly if both requested, or save separate files?
    # Simplest is to save the main one requested. If both, maybe just hourly?
    # Let's save hourly if present, else daily.

    final_df = dfs[0]
    print(f"Saving to {output_file}...")
    final_df.write_csv(output_file, include_header=True)
    print("Done.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch weather data from Open-Meteo.")
    parser.add_argument("--lat", required=True, type=float, help="Latitude")
    parser.add_argument("--lon", required=True, type=float, help="Longitude")
    parser.add_argument("--out", help="Output CSV filename")
    parser.add_argument("--historical", action="store_true", help="Fetch historical data (archive API)")  # noqa: E501
    parser.add_argument("--daily", action="store_true", help="Fetch daily data instead of hourly")  # noqa: E501
    parser.add_argument("--start", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", help="End date (YYYY-MM-DD)")

    args = parser.parse_args()
    fetch_open_meteo(args.lat, args.lon, args.out, args.historical, not args.daily, args.daily, args.start, args.end)  # noqa: E501
