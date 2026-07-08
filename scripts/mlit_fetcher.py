import argparse

import polars as pl
import requests


def fetch_land_prices(
    year: str,
    prefecture_code: str,
    city_code: str | None = None,
    output_file: str | None = None,
) -> None:
    """
    Fetches real-estate transaction prices (不動産取引価格情報) from the MLIT
    Real Estate Information Library API (endpoint XIT001).

    Note: this is transaction-price data, NOT 地価公示 (Chika Koji official land
    prices, which is a different endpoint).
    """

    try:
        from api_utils import require_api_key
    except ImportError:
        from .api_utils import require_api_key

    api_key = require_api_key("MLIT_API_KEY", "国土交通省 不動産情報ライブラリ", "https://www.reinfolib.mlit.go.jp/")

    base_url = "https://www.reinfolib.mlit.go.jp/ex-api/external/XIT001"

    params = {
        "year": year,
        "area": prefecture_code,
    }
    if city_code:
        params["city"] = city_code

    headers = {
        "Ocp-Apim-Subscription-Key": api_key
    }

    print(f"Fetching Land Transaction Prices for Year: {year}, Pref: {prefecture_code}...")  # noqa: E501

    try:
        response = requests.get(base_url, params=params, headers=headers)  # noqa: S113
        response.raise_for_status()
        data = response.json()
    except Exception as e:  # noqa: BLE001
        print(f"Error fetching data: {e}")
        return

    if data.get('status') == 'error':
         print(f"API Error: {data.get('message')}")
         return

    # Data is usually in 'data' key
    records = data.get('data', [])

    if not records:
        print("No data found.")
        return

    df = pl.DataFrame(records)

    if not output_file:
        output_file = f"mlit_land_prices_{year}_{prefecture_code}.csv"

    print(f"Saving to {output_file}...")
    df.write_csv(output_file, include_header=True)
    print("Done.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Land Transaction Prices from MLIT.")  # noqa: E501
    parser.add_argument("--year", required=True, help="Year (YYYY)")
    parser.add_argument("--pref", required=True, help="Prefecture Code (2 digits, e.g., 13 for Tokyo)")  # noqa: E501
    parser.add_argument("--city", help="City Code (5 digits)")
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    fetch_land_prices(args.year, args.pref, args.city, args.out)
