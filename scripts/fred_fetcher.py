import argparse
from datetime import UTC, datetime, timedelta

import polars as pl
import requests
from dotenv import load_dotenv

load_dotenv()

def fetch_fred_data(series_id: str, start_date: str | None = None, end_date: str | None = None, output_file: str | None = None) -> pl.DataFrame:  # noqa: E501
    """
    FRED (セントルイス連邦準備銀行) からマクロ経済指標を取得するわ。
    series_id の例:
    - 'UNRATE': 失業率
    - 'CPIAUCSL': 消費者物価指数
    - 'FEDFUNDS': 実効フェデラルファンド金利
    """
    try:
        from api_utils import require_api_key
    except ImportError:
        from .api_utils import require_api_key

    api_key = require_api_key("FRED_API_KEY", "FRED", "https://fred.stlouisfed.org/docs/api/api_key.html")

    if not start_date:
        start_date = (datetime.now(UTC) - timedelta(days=365*5)).strftime('%Y-%m-%d')
    if not end_date:
        end_date = datetime.now(UTC).strftime('%Y-%m-%d')

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
        response = requests.get(url, params=params)  # noqa: S113
        response.raise_for_status()
        data = response.json()

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

        if output_file:
            print(f"Saving to {output_file}...")
            df.write_csv(output_file)

        return df  # noqa: TRY300

    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error: {e.response.text if e.response else str(e)}")
        return pl.DataFrame()
    except Exception as e:  # noqa: BLE001
        print(f"Error fetching FRED data: {e}")
        return pl.DataFrame()

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Macroeconomic data from FRED API.")  # noqa: E501
    parser.add_argument("--series", required=True, help="FRED Series ID (e.g., UNRATE, CPIAUCSL).")  # noqa: E501
    parser.add_argument("--start", help="Start date (YYYY-MM-DD).")
    parser.add_argument("--end", help="End date (YYYY-MM-DD).")
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    fetch_fred_data(args.series, args.start, args.end, args.out)

if __name__ == "__main__":
    main()
