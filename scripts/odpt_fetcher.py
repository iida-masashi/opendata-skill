import argparse
import json

import polars as pl
import requests


def fetch_odpt_data(
    data_type: str, operator: str | None = None, output_file: str | None = None
) -> None:
    """
    Fetches data from ODPT (Public Transport Open Data Center).
    """

    try:
        from api_utils import require_api_key
    except ImportError:
        from .api_utils import require_api_key

    api_key = require_api_key("ODPT_API_KEY", "公共交通オープンデータセンター", "https://developer.odpt.org/")

    base_url = "https://api.odpt.org/api/v4/"

    # Construct endpoint based on data_type
    # Example types: odpt:Station, odpt:Train, odpt:Bus, odpt:Calendar
    endpoint = f"{base_url}{data_type}"

    params = {
        "acl:consumerKey": api_key
    }

    if operator:
        # Operator filter logic depends on the specific API call structure usually.
        # But for v4, filters are query params like 'odpt:operator=odpt.Operator:Toei'
        # The operator ID format is specific (e.g., 'odpt.Operator:Toei').
        # We'll assume the user provides the full ID or a partial match if we implement search.  # noqa: E501
        # For simplicity, let's pass it as a filter if provided.
        params["odpt:operator"] = operator

    print(f"Fetching ODPT Data: {data_type} (Operator: {operator})...")

    try:
        response = requests.get(endpoint, params=params)  # noqa: S113
        response.raise_for_status()
        data = response.json()
    except Exception as e:  # noqa: BLE001
        print(f"Error fetching ODPT data: {e}")
        return

    if not data:
        print("No data found.")
        return

    # Normalize JSON to DataFrame
    df = pl.DataFrame(data)

    # ネストした型 (List/Struct, 例: BusTimetable の時刻表オブジェクト) は
    # CSV に直接書けないため JSON 文字列へエンコードする。
    # to_list() で Python ネイティブ値に戻してから json.dumps する。
    nested = [
        c for c, dt in df.schema.items()
        if isinstance(dt, (pl.List, pl.Struct))
    ]
    for c in nested:
        encoded = [
            None if v is None else json.dumps(v, ensure_ascii=False, default=str)
            for v in df[c].to_list()
        ]
        df = df.with_columns(pl.Series(c, encoded, dtype=pl.Utf8))

    # Output filename
    if not output_file:
        safe_type = data_type.replace(':', '_')
        output_file = f"odpt_{safe_type}.csv"

    print(f"Saving to {output_file}...")
    try:
        df.write_csv(output_file, include_header=True)
    except Exception as e:  # noqa: BLE001
        print(f"Error saving CSV: {e}")

    print("Done.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Public Transport Data (ODPT).")
    parser.add_argument("--type", required=True, help="Data Type (e.g., 'odpt:Station', 'odpt:TrainInformation', 'odpt:BusTimetable')")  # noqa: E501
    parser.add_argument("--operator", help="Operator ID (e.g., 'odpt.Operator:Toei'). Optional.")  # noqa: E501
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    fetch_odpt_data(args.type, args.operator, args.out)
