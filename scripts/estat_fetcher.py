import argparse
import os
import sys
from typing import Any

import polars as pl
import requests
from dotenv import load_dotenv

try:
    from api_utils import rate_limited, retry_with_ratelimit
except ImportError:
    from .api_utils import rate_limited, retry_with_ratelimit

# Load environment variables
load_dotenv()

@retry_with_ratelimit
@rate_limited(max_calls=2, period=1.0)
def fetch_estat_data(
    app_id: str, stats_data_id: str, output_file: str | None = None, **kwargs: Any
) -> None:
    """
    Fetches statistical data from e-Stat API and saves it as a CSV file.
    Accepts additional kwargs like cdArea, cdCat01 for advanced filtering.
    """
    base_url = "http://api.e-stat.go.jp/rest/3.0/app/json/getStatsData"
    params: dict[str, Any] = {
        "appId": app_id,
        "statsDataId": stats_data_id,
        "metaGetFlg": "Y",
        "cntGetFlg": "N",
        "sectionHeaderFlg": "1",
    }
    if kwargs:
        params.update(kwargs)

    print(f"Fetching data for StatsDataId: {stats_data_id}...")
    try:
        response = requests.get(base_url, params=params, timeout=60)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        sys.exit(1)

    if data["GET_STATS_DATA"]["RESULT"]["STATUS"] != 0:
        print(f"API Error: {data['GET_STATS_DATA']['RESULT']['ERROR_MSG']}")
        sys.exit(1)

    statistical_data = data["GET_STATS_DATA"]["STATISTICAL_DATA"]
    if "DATA_INF" not in statistical_data:
        print("No data found in DATA_INF.")
        # Debug: Print keys to understand structure
        print(f"Available keys in STATISTICAL_DATA: {list(statistical_data.keys())}")
        if "RESULT" in statistical_data:  # Sometimes error info is here
            print(f"Result info: {statistical_data['RESULT']}")
        sys.exit(1)

    # Process Class Objects (Metadata for labels)
    class_objects = statistical_data.get("CLASS_INF", {}).get("CLASS_OBJ", [])
    class_map: dict[str, dict[str, Any]] = {}

    # Ensure class_objects is a list
    if isinstance(class_objects, dict):
        class_objects = [class_objects]

    for class_obj in class_objects:
        class_id = class_obj["@id"]
        class_name = class_obj["@name"]
        objects = class_obj.get("CLASS", [])
        if isinstance(objects, dict):
            objects = [objects]

        mapping = {obj["@code"]: obj["@name"] for obj in objects}
        class_map[class_id] = {"name": class_name, "mapping": mapping}

    # Process Data Objects
    data_inf = statistical_data.get("DATA_INF", {})

    # Try DATA_OBJ first, then VALUE
    data_objects = data_inf.get("DATA_OBJ", [])
    if not data_objects:
        data_objects = data_inf.get("VALUE", [])

    if isinstance(data_objects, dict):
        data_objects = [data_objects]

    if not data_objects:
        print("No data found in DATA_OBJ or VALUE.")
        sys.exit(0)

    print(f"Debug: Found {len(data_objects)} items (DATA_OBJ or VALUE)")

    records: list[dict[str, Any]] = []
    for item in data_objects:
        record: dict[str, Any] = {}
        for key, value in item.items():
            # Map keys to human readable names if possible, else keep code
            if key.startswith("@"):
                clean_key = key[1:]  # remove @
                if clean_key in class_map:
                    # Map value code to name
                    mapped_value = class_map[clean_key]["mapping"].get(value, value)
                    col_name = class_map[clean_key]["name"]
                    record[col_name] = mapped_value
                elif clean_key == "unit":
                    record["unit"] = value
                else:
                    record[clean_key] = value
            elif key == "$":
                # 観測値。下の Value handling で 'value' 列として扱うので
                # ここで重複した '$' 列を作らない。
                continue
            else:
                record[key] = value

        # Value handling
        if "$" in item:
            record["value"] = item["$"]

        records.append(record)

    df = pl.DataFrame(records)

    # Date Formatting
    time_col = None
    for col in df.columns:
        if "時間" in col or "Time" in col or "Year" in col:
            time_col = col
            break

    if time_col:
        print(f"Formatting date column: {time_col}")

        def format_date(val: Any) -> Any:
            s_val = str(val)
            if not s_val.isdigit():
                return val
            if len(s_val) >= 4:
                year = s_val[:4]
                month = "01"
                day = "01"
                # Simple logic: assume YYYY or YYYYMM or YYYYMMDD
                if len(s_val) >= 6:
                    month = s_val[4:6]
                if len(s_val) >= 8:
                    day = s_val[6:8]
                return f"{year}{month}{day}"
            return val

        df = df.with_columns(
            pl.col(time_col).map_elements(format_date, return_dtype=pl.String)
        )

    # Output filename
    if not output_file:
        output_file = f"estat_data_{stats_data_id}.csv"

    print(f"Saving to {output_file}...")
    # Polars write_csv uses UTF-8
    try:
        df.write_csv(output_file, include_header=True)
    except Exception as e:
        print(f"Error saving CSV: {e}")

    print("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch e-Stat data and save as CSV.")
    parser.add_argument(
        "--appId",
        help="e-Stat Application ID (default: env ESTAT_API_KEY)",
        default=os.getenv("ESTAT_API_KEY"),
    )
    parser.add_argument("--statsDataId", required=True, help="Statistics Data ID")
    parser.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Additional API filter, e.g. --param cdArea=13000 --param cdCat01=001 (repeatable)",
    )
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()

    try:
        from api_utils import require_api_key
    except ImportError:
        from .api_utils import require_api_key

    app_id = args.appId or require_api_key("ESTAT_API_KEY", "e-Stat", "https://www.e-stat.go.jp/api/")

    extra: dict[str, str] = {}
    for kv in args.param:
        if "=" not in kv:
            parser.error(f"--param must be KEY=VALUE, got: {kv}")
        k, v = kv.split("=", 1)
        extra[k] = v

    fetch_estat_data(app_id, args.statsDataId, args.out, **extra)


if __name__ == "__main__":
    main()
