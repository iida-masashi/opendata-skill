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


def fetch_plateau_model(query: str, output_file: str | None = None) -> None:
    """
    Fetches PLATEAU 3D City Model metadata.
    """
    base_url = "https://www.geospatial.jp/ckan/api/3/action/package_search"

    # Construct search query
    # PLATEAU datasets usually look like "PLATEAU 13101 (千代田区)"
    search_q = f"PLATEAU {query}"

    params: dict[str, Any] = {
        "q": search_q,
        "rows": 20
    }

    print(f"Searching PLATEAU dataset for: {query}...")
    try:
        response = _get_with_retry(base_url, params=params)
        data = response.json()
    except Exception as e:  # noqa: BLE001
        print(f"Error searching data: {e}")
        return

    results = data.get('result', {}).get('results', [])
    if not results:
        print("No PLATEAU dataset found for this code.")
        return

    # Just take the first result as it's likely the city's main package
    package = results[0]
    title = package.get('title')
    resources = package.get('resources', [])

    print(f"Found Dataset: {title}")

    # Filter for interesting resources (e.g., '3D Tiles', 'GeoJSON', 'CityGML')
    # Use Case: "Flood Risk" -> 'disaster_risk'?
    # Let's list available resources and maybe download a small one (like Dictionary or Metadata)  # noqa: E501
    # or just output the URLs to a CSV so the user can download manually.

    resource_list = []
    for res in resources:
        resource_list.append({
            'name': res.get('name'),
            'format': res.get('format'),
            'url': res.get('url'),
            'description': res.get('description')
        })

    df = pl.DataFrame(resource_list)

    if not output_file:
        safe_query = query.replace(' ', '_')
        output_file = f"plateau_resources_{safe_query}.csv"

    print(f"Saving resource list to {output_file}...")
    df.write_csv(output_file, include_header=True)
    print("Done. Use these URLs to download specific 3D data.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch PLATEAU Dataset Metadata.")
    parser.add_argument("--query", required=True, help="City Code (5 digits) or City Name")  # noqa: E501
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    fetch_plateau_model(args.query, args.out)
