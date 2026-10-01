import argparse
import urllib.parse

import polars as pl
import requests  # noqa: F401 - テストが gsi_fetcher.requests.get を patch する

from api_utils import cli_entry, save_output
from api_utils import get_with_retry as _get_with_retry


def fetch_gsi_msearch(query: str, output_file: str | None = None) -> pl.DataFrame:
    """
    Fetches location data (lat/lon) from GSI Maps (Geospatial Information Authority of Japan) Msearch API.
    No API key required.
    """  # noqa: E501
    base_url = "https://msearch.gsi.go.jp/address-search/AddressSearch"
    params = {"q": query}

    print(f"Searching location for: {query}...")
    response = _get_with_retry(base_url, params=params)
    data = response.json()

    if not data:
        print("No location found.")
        return pl.DataFrame()

    # Extract relevant fields
    # API returns: [{"geometry": {"coordinates": [lon, lat], "type": "Point"}, "properties": {"addressCode": "", "title": "..."}}, ...]  # noqa: E501

    records = []
    for item in data:
        coords = item.get('geometry', {}).get('coordinates', [])
        props = item.get('properties', {})

        if len(coords) == 2:  # noqa: PLR2004
            records.append({
                'Name': props.get('title'),
                'AddressCode': props.get('addressCode'),
                'Longitude': coords[0],
                'Latitude': coords[1]
            })

    df = pl.DataFrame(records)
    save_output(df, output_file)
    return df

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Lat/Lon from GSI Maps (Msearch).")  # noqa: E501
    parser.add_argument("query", help="Place name or address (e.g., 'Tokyo Tower', 'Chiyoda-ku')")  # noqa: E501
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    output_file = args.out or f"gsi_{urllib.parse.quote(args.query, safe='')}.csv"
    fetch_gsi_msearch(args.query, output_file)

if __name__ == "__main__":
    cli_entry(main)
