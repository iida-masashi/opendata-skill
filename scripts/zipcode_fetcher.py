import argparse

import polars as pl
import requests  # noqa: F401 - テストが zipcode_fetcher.requests.get を patch する

from api_utils import cli_entry, save_output
from api_utils import get_with_retry as _get_with_retry


def fetch_zipcode(zipcode: str, output_file: str | None = None) -> pl.DataFrame:
    """
    Fetches address information from a zipcode using ZipCloud API.
    No API key required.
    """
    base_url = "http://zipcloud.ibsnet.co.jp/api/search"
    params = {"zipcode": zipcode}

    print(f"Searching address for zipcode: {zipcode}...")
    response = _get_with_retry(base_url, params=params)
    data = response.json()

    # ZipCloud はエラーも HTTP 200 + status (400: 入力エラー / 500: サーバエラー) で返す。
    status = data.get('status')
    if status != 200:  # noqa: PLR2004
        exc = ValueError if status == 400 else RuntimeError  # noqa: PLR2004
        raise exc(f"ZipCloud API error (status={status}): {data.get('message')}")

    results = data.get('results')
    if not results:
        print("No address found for this zipcode.")
        return pl.DataFrame()

    df = pl.DataFrame(results)
    save_output(df, output_file)
    return df

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch address from zipcode (ZipCloud).")  # noqa: E501
    parser.add_argument("zipcode", help="7-digit zipcode (e.g., 1000001)")
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    fetch_zipcode(args.zipcode, args.out or f"address_{args.zipcode}.csv")

if __name__ == "__main__":
    cli_entry(main)
