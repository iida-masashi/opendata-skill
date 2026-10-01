import argparse
import urllib.parse
from typing import Any

import polars as pl
import requests  # noqa: F401 - テストが ckan_fetcher.requests.get を patch する

from api_utils import cli_entry, save_output
from api_utils import get_with_retry as _get_with_retry


def search_ckan(
    base_url: str, query: str, rows: int = 10, output_file: str | None = None
) -> pl.DataFrame:
    """
    Searches a CKAN-based portal (like e-Gov Data Portal) for datasets.
    """

    # API Endpoint for package search
    api_url = f"{base_url.rstrip('/')}/api/3/action/package_search"

    params: dict[str, Any] = {"q": query, "rows": rows}

    print(f"Searching {base_url} for '{query}'...")

    response = _get_with_retry(api_url, params=params, timeout=30)
    data = response.json()

    if not data.get("success"):
        raise RuntimeError(f"CKAN API error: {data.get('error')}")

    results: list[dict[str, Any]] = data.get("result", {}).get("results", [])

    if not results:
        print("No datasets found.")
        return pl.DataFrame()

    print(f"Found {len(results)} datasets. Extracting CSV resources...")

    resource_list: list[dict[str, Any]] = []
    for package in results:
        pkg_title = package.get("title")
        # organization / format は null で返ることがある。
        organization = (package.get("organization") or {}).get("title")

        for res in package.get("resources") or []:
            fmt = (res.get("format") or "").upper()
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
        return pl.DataFrame()

    df = pl.DataFrame(resource_list)
    save_output(df, output_file)
    return df


def main() -> None:
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
    output_file = args.out or f"ckan_search_{urllib.parse.quote(args.query, safe='')}.csv"
    df = search_ckan(args.url, args.query, args.rows, output_file)
    if not df.is_empty():
        print("Done. You can now download specific files using the URLs in the CSV.")
        print("Example: curl -O <URL>")


if __name__ == "__main__":
    cli_entry(main)
