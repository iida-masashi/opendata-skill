import argparse
import urllib.parse

import polars as pl
import requests


def fetch_gsi_msearch(query: str, output_file: str | None = None) -> None:
    """
    Fetches location data (lat/lon) from GSI Maps (Geospatial Information Authority of Japan) Msearch API.
    No API key required.
    """  # noqa: E501
    base_url = "https://msearch.gsi.go.jp/address-search/AddressSearch"
    params = {"q": query}

    print(f"Searching location for: {query}...")
    try:
        response = requests.get(base_url, params=params)  # noqa: S113
        response.raise_for_status()
        data = response.json()
    except Exception as e:  # noqa: BLE001
        print(f"Error fetching GSI data: {e}")
        return

    if not data:
        print("No location found.")
        return

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

    if not output_file:
        safe_query = urllib.parse.quote(query, safe='')
        output_file = f"gsi_{safe_query}.csv"

    print(f"Saving to {output_file}...")
    df.write_csv(output_file, include_header=True)
    print("Done.")

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Lat/Lon from GSI Maps (Msearch).")  # noqa: E501
    parser.add_argument("query", help="Place name or address (e.g., 'Tokyo Tower', 'Chiyoda-ku')")  # noqa: E501
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    fetch_gsi_msearch(args.query, args.out)

if __name__ == "__main__":
    main()
