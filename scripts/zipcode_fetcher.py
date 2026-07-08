import argparse

import polars as pl
import requests


def fetch_zipcode(zipcode: str, output_file: str | None = None) -> None:
    """
    Fetches address information from a zipcode using ZipCloud API.
    No API key required.
    """
    base_url = "http://zipcloud.ibsnet.co.jp/api/search"
    params = {"zipcode": zipcode}

    print(f"Searching address for zipcode: {zipcode}...")
    try:
        response = requests.get(base_url, params=params)  # noqa: S113
        response.raise_for_status()
        data = response.json()
    except Exception as e:  # noqa: BLE001
        print(f"Error fetching zipcode data: {e}")
        return

    if data.get('status') != 200:  # noqa: PLR2004
        print(f"API Error: {data.get('message')}")
        return

    results = data.get('results')
    if not results:
        print("No address found for this zipcode.")
        return

    df = pl.DataFrame(results)

    if not output_file:
        output_file = f"address_{zipcode}.csv"

    print(f"Saving to {output_file}...")
    df.write_csv(output_file, include_header=True)
    print("Done.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch address from zipcode (ZipCloud).")  # noqa: E501
    parser.add_argument("zipcode", help="7-digit zipcode (e.g., 1000001)")
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    fetch_zipcode(args.zipcode, args.out)
