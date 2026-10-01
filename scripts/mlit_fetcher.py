import argparse

import polars as pl
import requests  # noqa: F401 - テストが mlit_fetcher.requests.get を patch する
from dotenv import load_dotenv

from api_utils import cli_entry, require_api_key, save_output
from api_utils import get_with_retry as _get_with_retry

load_dotenv()


def fetch_land_prices(
    year: str,
    prefecture_code: str,
    city_code: str | None = None,
    output_file: str | None = None,
) -> pl.DataFrame:
    """
    Fetches real-estate transaction prices (不動産取引価格情報) from the MLIT
    Real Estate Information Library API (endpoint XIT001).

    Note: this is transaction-price data, NOT 地価公示 (Chika Koji official land
    prices, which is a different endpoint).
    """
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

    response = _get_with_retry(base_url, params=params, headers=headers)
    data = response.json()

    if data.get('status') == 'error':
        raise RuntimeError(f"MLIT API error: {data.get('message')}")

    # Data is usually in 'data' key
    records = data.get('data', [])

    if not records:
        print("No data found.")
        return pl.DataFrame()

    # 取引レコードは種別により持つキーが異なるため、全行でスキーマを推論する。
    df = pl.DataFrame(records, infer_schema_length=None)
    save_output(df, output_file)
    return df

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Land Transaction Prices from MLIT.")  # noqa: E501
    parser.add_argument("--year", required=True, help="Year (YYYY)")
    parser.add_argument("--pref", required=True, help="Prefecture Code (2 digits, e.g., 13 for Tokyo)")  # noqa: E501
    parser.add_argument("--city", help="City Code (5 digits)")
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    output_file = args.out or f"mlit_land_prices_{args.year}_{args.pref}.csv"
    fetch_land_prices(args.year, args.pref, args.city, output_file)

if __name__ == "__main__":
    cli_entry(main)
