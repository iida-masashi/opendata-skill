import argparse

import polars as pl
import requests
from dotenv import load_dotenv

from api_utils import (
    cli_entry,
    default_date_range,
    require_api_key,
    save_output,
)
from api_utils import get_with_retry_redacted as _get_redacted

load_dotenv()

def fetch_fred_data(series_id: str, start_date: str | None = None, end_date: str | None = None, output_file: str | None = None) -> pl.DataFrame:  # noqa: E501
    """
    FRED (セントルイス連邦準備銀行) からマクロ経済指標を取得するわ。
    series_id の例:
    - 'UNRATE': 失業率
    - 'CPIAUCSL': 消費者物価指数
    - 'FEDFUNDS': 実効フェデラルファンド金利
    """
    api_key = require_api_key("FRED_API_KEY", "FRED", "https://fred.stlouisfed.org/docs/api/api_key.html")

    start_date, end_date = default_date_range(start_date, end_date, days=365*5)

    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start_date,
        "observation_end": end_date
    }

    print(f"Fetching FRED data for {series_id} from {start_date} to {end_date}...")
    try:
        # 例外メッセージには api_key 入りの URL が含まれるため伏せる。
        response = _get_redacted(url, [api_key], params=params)
    except requests.exceptions.RequestException as e:
        raise type(e)(f"FRED {series_id}: {e}", response=e.response) from None
    data = response.json()

    if "error_message" in data:
        raise RuntimeError(f"FRED API error for {series_id}: {data['error_message']}")

    observations = data.get("observations", [])
    if not observations:
        print("No data found for the given series and date range.")
        return pl.DataFrame()

    # 不要な列を省き、Polars DataFrameへ
    records = [
        {"date": obs["date"], "value": float(obs["value"]) if obs["value"] != '.' else None}  # noqa: E501
        for obs in observations
    ]

    df = pl.DataFrame(records)
    df = df.drop_nulls() # 欠損値は削除
    df = df.with_columns(pl.lit(series_id).alias("series_id"))

    save_output(df, output_file)
    return df


def fetch_fred_alias(
    alias_map: dict[str, str],
    series: str,
    start_date: str | None = None,
    end_date: str | None = None,
    output_file: str | None = None,
) -> pl.DataFrame:
    """エイリアス名（alias_map のキー、大文字小文字無視）または FRED 系列IDで取得し、series 列にエイリアスを付ける。"""
    series_id = alias_map.get(series.lower(), series)
    df = fetch_fred_data(series_id=series_id, start_date=start_date, end_date=end_date)
    if df.is_empty():
        return df

    df = df.with_columns(pl.lit(series).alias("series"))
    save_output(df, output_file)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Macroeconomic data from FRED API.")  # noqa: E501
    parser.add_argument("--series", required=True, help="FRED Series ID (e.g., UNRATE, CPIAUCSL).")  # noqa: E501
    parser.add_argument("--start", help="Start date (YYYY-MM-DD).")
    parser.add_argument("--end", help="End date (YYYY-MM-DD).")
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    fetch_fred_data(args.series, args.start, args.end, args.out)

if __name__ == "__main__":
    cli_entry(main)
