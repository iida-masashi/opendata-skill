import argparse
from typing import Any

import polars as pl
import requests


def fetch_resas_population(
    pref_code: int, city_code: str = "all", output_file: str | None = None
) -> None:
    """
    Fetches Population Composition from RESAS API.
    """
    try:
        from api_utils import require_api_key
    except ImportError:
        from .api_utils import require_api_key

    api_key = require_api_key("RESAS_API_KEY", "RESAS API", "https://opendata.resas-portal.go.jp/")

    base_url = "https://opendata.resas-portal.go.jp/api/v1/population/composition/perYear"

    params: dict[str, Any] = {
        "prefCode": pref_code,
        "cityCode": city_code # 'all' for all cities in pref, or specific code
    }

    headers = {
        "X-API-KEY": api_key
    }

    print(f"Fetching Population Composition (RESAS) for Pref: {pref_code}, City: {city_code}...")  # noqa: E501

    try:
        response = requests.get(base_url, params=params, headers=headers)  # noqa: S113
        response.raise_for_status()
        data = response.json()
    except Exception as e:  # noqa: BLE001
        print(f"Error fetching data: {e}")
        return

    result = data.get('result')
    if not result:
        print(f"No result found. Message: {data.get('message')}")
        return

    # Structure: result -> data -> [ {label: 'Total', data: [{year, value}, ...]}, {label: 'Young', ...} ]  # noqa: E501
    # We want a flattened DataFrame: Year, Category, Value

    records = []

    # Boundary Year handling? Usually 2015/2020/2025 etc.
    # The API returns 'boundaryYear' but for simple CSV we just want the data points.

    categories = result.get('data', [])
    for category in categories:
        label = category.get('label')
        points = category.get('data', [])
        for point in points:
            year = point.get('year')
            value = point.get('value')
            records.append({'Year': year, 'Category': label, 'Value': value, 'PrefCode': pref_code, 'CityCode': city_code})  # noqa: E501

    df = pl.DataFrame(records)

    if not output_file:
        output_file = f"resas_pop_{pref_code}_{city_code}.csv"

    print(f"Saving to {output_file}...")
    df.write_csv(output_file, include_header=True)
    print("Done.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Population Composition from RESAS.")  # noqa: E501
    parser.add_argument("--pref", required=True, type=int, help="Prefecture Code (1-47)")  # noqa: E501
    parser.add_argument("--city", default="all", help="City Code (5 digits or 'all'). Default: 'all' (Prefecture total)")  # noqa: E501
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    fetch_resas_population(args.pref, args.city, args.out)
