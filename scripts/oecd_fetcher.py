import argparse
from typing import Any

import polars as pl
import requests

try:
    from api_utils import rate_limited, retry_with_ratelimit
except ImportError:
    from .api_utils import rate_limited, retry_with_ratelimit

# OECD Dataset Mapping (Verified for 2024-2025 SDMX API)
# Pattern: {AgencyID},{DataflowID},{Version}
OECD_DATASETS = {
    "MEI": {
        "full_id": "OECD.SDD.STES,DSD_KEI@DF_KEI,4.0",
        "description": "Key Short-Term Economic Indicators (MEI Replacement)"
    },
    "KEI": {
        "full_id": "OECD.SDD.STES,DSD_KEI@DF_KEI,4.0",
        "description": "Key Short-Term Economic Indicators"
    },
    "QNA": {
        "full_id": "OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA_EXPENDITURE_USD,1.1",
        "description": "Quarterly National Accounts (Expenditure, USD)"
    },
    "QNA_GDP": {
        "full_id": "OECD.SDD.NAD,DSD_NAMAIN10@DF_TABLE1,2.0",
        "description": "Quarterly GDP and Main Components"
    },
    "TUD": {
        "full_id": "OECD.ELS.SAE,DSD_TUD_CBC@DF_TUD,1.0",
        "description": "Trade Union Density"
    },
    "CLI": {
        "full_id": "OECD.SDD.STES,DSD_STES@DF_CLI,4.1",
        "description": "Composite Leading Indicators"
    },
    "INDSERV": {
        "full_id": "OECD.SDD.STES,DSD_STES@DF_INDSERV,4.3",
        "description": "Production and Sales in Industry and Services"
    },
    "BOP": {
        "full_id": "OECD.SDD.TPS,DSD_BOP@DF_BOP,1.0",
        "description": "Balance of Payments"
    },
    "PRICES": {
        "full_id": "OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0",
        "description": "Consumer Price Indices (CPI)"
    }
}


def parse_sdmx_json(data: dict[str, Any]) -> pl.DataFrame:
    """
    Parses SDMX-JSON (V2) response from OECD API into a Polars DataFrame.
    Supports SDMX 3.0 (structures list).
    """
    try:
        # Handle SDMX 3.0 (V2) structures list or V1 single structure
        if "data" in data and "structures" in data["data"]:
            structure = data["data"]["structures"][0]
        elif "data" in data and "structure" in data["data"]:
            structure = data["data"]["structure"]
        else:
            raise ValueError("No structure found in JSON response")

        dimensions = structure["dimensions"]["observation"]
        datasets = data["data"]["dataSets"]
    except (KeyError, IndexError, ValueError) as e:
        raise ValueError(f"Invalid SDMX-JSON structure: {e}") from e

    # Map dimension indices to their actual values
    dim_maps = []
    for dim in dimensions:
        dim_maps.append({str(i): v["id"] for i, v in enumerate(dim["values"])})

    dim_names = [dim["id"] for dim in dimensions]

    rows = []
    for dataset in datasets:
        observations = dataset.get("observations", {})
        for key, value in observations.items():
            # key is like "0:0:1:0"
            indices = key.split(":")
            row = {}
            for i, idx in enumerate(indices):
                if i < len(dim_names):
                    dim_name = dim_names[i]
                    row[dim_name] = dim_maps[i].get(idx, idx)

            # value is like [100.5, 0, 0, ...] where [0] is the observation value
            if isinstance(value, list) and len(value) > 0:
                row["Value"] = value[0]
            else:
                row["Value"] = None

            rows.append(row)

    if not rows:
        return pl.DataFrame()

    return pl.DataFrame(rows)


@retry_with_ratelimit
@rate_limited(max_calls=1, period=1.0)
def fetch_oecd_data(
    dataset_code: str,
    countries: str = "all",
    start_year: int | None = None,
    end_year: int | None = None,
    output_file: str | None = None,
) -> None:
    """
    Fetches OECD data using the new SDMX-JSON API (sdmx.oecd.org).
    """
    info = OECD_DATASETS.get(dataset_code.upper())
    if not info:
        print(f"Warning: Unknown dataset code '{dataset_code}'. Attempting direct fetch with ID...")
        full_id = dataset_code # Expect user to provide full Agency,Dataset,Version
    else:
        full_id = info['full_id']
        print(f"Fetching {info['description']} ({dataset_code})...")

    # Construct API URL
    # Format: https://sdmx.oecd.org/public/rest/data/{full_id}/all
    base_url = f"https://sdmx.oecd.org/public/rest/data/{full_id}/all"

    params = {
        "format": "jsondata",
        "dimensionAtObservation": "AllDimensions"
    }

    if start_year:
        params["startPeriod"] = f"{start_year}"
    if end_year:
        params["endPeriod"] = f"{end_year}"

    print(f"Requesting: {base_url}")
    try:
        response = requests.get(base_url, params=params, timeout=60)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        # 一時的エラー (429/5xx/接続) は再送出して @retry_with_ratelimit に
        # 任せる。リトライ枯渇後はそのまま送出され呼び出し側が検知できる。
        print(f"Error fetching data from OECD API: {e}")
        print("Note: Ensure the dataset code is correct and the API is reachable.")
        raise

    print("Parsing JSON data...")
    df = parse_sdmx_json(data)

    if df.is_empty():
        print("No data found.")
        return

    # Post-filtering by country if requested
    if countries != 'all':
        country_list = [c.strip() for c in countries.split(',')]
        # Detect country column (usually REF_AREA, LOCATION, or REPORTING_COUNTRY)
        country_col = None
        for col in ['REF_AREA', 'LOCATION', 'REPORTING_COUNTRY']:
            if col in df.columns:
                country_col = col
                break

        if country_col:
            df = df.filter(pl.col(country_col).is_in(country_list))
            print(f"Filtered to countries: {countries} ({len(df)} rows remaining)")
        else:
            print("Warning: Could not identify country column for filtering. Columns found:", df.columns)

    if not output_file:
        output_file = f"oecd_{dataset_code.lower()}.csv"

    print(f"Saving {len(df)} rows to {output_file}...")
    df.write_csv(output_file, include_header=True)
    print("Done.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch OECD Data using the new SDMX-JSON API (2024+ Edition).")
    parser.add_argument("--dataset", required=True, help="OECD Dataset Code (e.g., 'MEI', 'QNA', 'TUD', 'CLI')")
    parser.add_argument("--countries", default="all", help="Country Codes (ISO3, comma-separated). Default: 'all'.")
    parser.add_argument("--start", type=int, help="Start Year (YYYY)")
    parser.add_argument("--end", type=int, help="End Year (YYYY)")
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    fetch_oecd_data(args.dataset, args.countries, args.start, args.end, args.out)
