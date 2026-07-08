import argparse
import urllib.parse
from typing import Any

import polars as pl
import requests


def search_ckan(
    base_url: str, query: str, rows: int = 10, output_file: str | None = None
) -> None:
    """
    Searches a CKAN-based portal (like e-Gov Data Portal) for datasets.
    """

    # API Endpoint for package search
    api_url = f"{base_url.rstrip('/')}/api/3/action/package_search"

    params: dict[str, Any] = {"q": query, "rows": rows}

    print(f"Searching {base_url} for '{query}'...")

    try:
        response = requests.get(api_url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Error searching CKAN: {e}")
        return

    if not data.get("success"):
        print("CKAN API Error: Request failed.")
        return

    results: list[dict[str, Any]] = data.get("result", {}).get("results", [])

    if not results:
        print("No datasets found.")
        return

    print(f"Found {len(results)} datasets. Extracting CSV resources...")

    resource_list: list[dict[str, Any]] = []
    for package in results:
        pkg_title = package.get("title")
        organization = package.get("organization", {}).get("title")

        for res in package.get("resources", []):
            fmt = res.get("format", "").upper()
            if "CSV" in fmt:
                resource_list.append(
                    {
                        "Dataset": pkg_title,
                        "Organization": organization,
                        "Resource Name": res.get("name"),
                        "Format": fmt,
                        "URL": res.get("url"),
                        "Description": res.get("description"),
                        "Last Modified": res.get("last_modified") or res.get("created"),
                    }
                )

    if not resource_list:
        print("No CSV resources found in the search results.")
        return

    df = pl.DataFrame(resource_list)

    # Output filename
    if not output_file:
        safe_query = urllib.parse.quote(query, safe="")
        output_file = f"ckan_search_{safe_query}.csv"

    print(f"Saving resource list to {output_file}...")
    try:
        df.write_csv(output_file, include_header=True)
    except Exception as e:
        print(f"Error saving CSV: {e}")

    print("Done. You can now download specific files using the URLs in the CSV.")
    print("Example: curl -O <URL>")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Search CKAN Open Data Portals (e.g., e-Gov)."
    )
    parser.add_argument(
        "--query", required=True, help="Search query (e.g., 'AED', '人口', '避難所')"
    )
    parser.add_argument(
        "--url",
        default="https://data.e-gov.go.jp/data",
        help="CKAN Base URL. Default: e-Gov Data Portal",
    )
    parser.add_argument(
        "--rows", type=int, default=10, help="Number of results to fetch"
    )
    parser.add_argument("--out", help="Output CSV filename for the resource list")

    args = parser.parse_args()
    search_ckan(args.url, args.query, args.rows, args.out)
