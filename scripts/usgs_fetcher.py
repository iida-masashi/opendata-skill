import argparse
from datetime import UTC, datetime

import polars as pl
import requests  # noqa: F401 - テストが usgs_fetcher.requests.get を patch する

from api_utils import cli_entry, default_date_range, save_output
from api_utils import get_with_retry as _get_with_retry

# USGS Earthquake API (APIキー不要)
BASE_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"


def fetch_usgs_earthquakes(
    start_date: str | None = None,
    end_date: str | None = None,
    min_magnitude: float = 4.5,
    max_magnitude: float | None = None,
    min_lat: float | None = None,
    max_lat: float | None = None,
    min_lon: float | None = None,
    max_lon: float | None = None,
    output_file: str | None = None,
) -> pl.DataFrame:
    """
    USGS Earthquake API からグローバル地震データを取得するわ。
    APIキー不要、無料、リアルタイム。
    海外工場・サプライヤ拠点の地震リスク評価に使用。
    J-SHISは日本特化、こちらはグローバルカバレッジ。
    """
    start_date, end_date = default_date_range(start_date, end_date, 30)

    params: dict = {
        "format": "geojson",
        "starttime": start_date,
        "endtime": end_date,
        "minmagnitude": min_magnitude,
        "orderby": "time",
        "limit": 20000,
    }
    if max_magnitude:
        params["maxmagnitude"] = max_magnitude
    if min_lat is not None and max_lat is not None:
        params["minlatitude"] = min_lat
        params["maxlatitude"] = max_lat
    if min_lon is not None and max_lon is not None:
        params["minlongitude"] = min_lon
        params["maxlongitude"] = max_lon

    print(f"Fetching USGS earthquakes: M>={min_magnitude}, {start_date}→{end_date}...")
    response = _get_with_retry(BASE_URL, params=params)
    data = response.json()

    features = data.get("features", [])
    if not features:
        print("No earthquakes found.")
        return pl.DataFrame()

    records = []
    for f in features:
        props = f.get("properties", {})
        coords = f.get("geometry", {}).get("coordinates", [None, None, None])
        epoch_ms = props.get("time")
        dt_str = None
        if epoch_ms is not None:
            dt_str = datetime.fromtimestamp(epoch_ms / 1000, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
        records.append({
            "date": dt_str,
            "magnitude": props.get("mag"),
            "place": props.get("place"),
            "longitude": coords[0],
            "latitude": coords[1],
            "depth_km": coords[2],
            "tsunami": props.get("tsunami"),
            "significance": props.get("sig"),
            "type": props.get("type"),
            "url": props.get("url"),
        })

    df = pl.DataFrame(records)

    save_output(df, output_file)

    print(f"[USGS] {df.height} earthquakes fetched.")
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch global earthquake data from USGS.")
    parser.add_argument("--start", help="Start date (YYYY-MM-DD).")
    parser.add_argument("--end", help="End date (YYYY-MM-DD).")
    parser.add_argument("--min-mag", type=float, default=4.5, help="Minimum magnitude.")
    parser.add_argument("--max-mag", type=float, help="Maximum magnitude.")
    parser.add_argument("--min-lat", type=float)
    parser.add_argument("--max-lat", type=float)
    parser.add_argument("--min-lon", type=float)
    parser.add_argument("--max-lon", type=float)
    parser.add_argument("--out", help="Output CSV filename.")
    args = parser.parse_args()
    fetch_usgs_earthquakes(
        start_date=args.start,
        end_date=args.end,
        min_magnitude=args.min_mag,
        max_magnitude=args.max_mag,
        min_lat=args.min_lat,
        max_lat=args.max_lat,
        min_lon=args.min_lon,
        max_lon=args.max_lon,
        output_file=args.out,
    )


if __name__ == "__main__":
    cli_entry(main)
