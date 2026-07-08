import argparse
import xml.etree.ElementTree as ET
from typing import Any

import polars as pl
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def fetch_corporate_info(
    query: str, mode: str = "number", output_file: str | None = None
) -> None:
    """
    Fetches corporate information from National Tax Agency Corporate Number API.
    Requirement: CORP_API_KEY in .env
    """
    try:
        from api_utils import require_api_key
    except ImportError:
        from .api_utils import require_api_key

    api_key = require_api_key("CORP_API_KEY", "gBizINFO / 法人番号システム", "https://www.houjin-bangou.nta.go.jp/")

    # API Version 4. type=12 is the only structured format and it is XML
    # (root <corporations> with repeated <corporation> children); the API
    # offers no JSON output.
    if mode == "number":
        # Search by 13-digit corporate number
        base_url = "https://api.houjin-bangou.nta.go.jp/4/num"
        params: dict[str, Any] = {
            "id": api_key,
            "number": query,
            "type": "12",  # XML format
            "history": "0",  # No history
        }
    else:
        # Search by name
        base_url = "https://api.houjin-bangou.nta.go.jp/4/name"
        params = {
            "id": api_key,
            "name": query,
            "type": "12",  # XML format
            "mode": "2",  # Partial match
            "target": "1",  # Current records
        }

    print(f"Searching Corporate Info (Mode: {mode}, Query: {query})...")
    try:
        response = requests.get(base_url, params=params, timeout=30)
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except Exception as e:
        print(f"Error fetching corporate data: {e}")
        return

    # Parse XML: each <corporation> becomes a flat dict of its child tags.
    # Namespace-agnostic ({*}) in case the response carries a default xmlns;
    # child tags are stripped of any namespace prefix.
    def _local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    records: list[dict[str, Any]] = []
    for corp in root.findall(".//{*}corporation"):
        record = {_local(child.tag): (child.text or "") for child in corp}
        if record:
            records.append(record)

    if not records:
        print("No corporate data found.")
        return

    df = pl.DataFrame(records)

    if not output_file:
        safe_query = query.replace(" ", "_")
        output_file = f"corp_{safe_query}.csv"

    print(f"Saving to {output_file}...")
    df.write_csv(output_file, include_header=True)
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch Corporate Info (National Tax Agency)."
    )
    parser.add_argument("query", help="Corporate Number (13 digits) or Company Name")
    parser.add_argument(
        "--name", action="store_true", help="Search by name instead of number"
    )
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    mode = "name" if args.name else "number"
    fetch_corporate_info(args.query, mode, args.out)
