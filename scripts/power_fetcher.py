import argparse
import datetime

import polars as pl
import requests

from api_utils import cli_entry, save_output
from api_utils import get_with_retry as _get_with_retry

TEPCO_CSV_BASE = "https://www.tepco.co.jp/forecast/html/images"


def _download_tepco_csv() -> requests.Response:
    """当年 → 前年の年次 CSV を試し、どちらも 404（未公開）なら日次最新 CSV を取る。

    404 以外の失敗（5xx・接続エラー等）はフォールバックせずに例外を伝播させる。
    """
    current_year = datetime.datetime.now().year  # noqa: DTZ005
    for year in [current_year, current_year - 1]:
        url = f"{TEPCO_CSV_BASE}/juyo-{year}.csv"
        print(f"Trying URL: {url}...")
        try:
            return _get_with_retry(url)
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:  # noqa: PLR2004
                continue
            raise

    # The daily-latest fallback is not a full year's data.
    url = f"{TEPCO_CSV_BASE}/juyo-d-j.csv"
    print(f"⚠️ Yearly CSVs not found (404). Falling back to daily latest: {url}")
    return _get_with_retry(url)


def fetch_power_usage(
    area: str = "tokyo", date: str | None = None, output_file: str | None = None
) -> pl.DataFrame:
    """
    Fetches electric power usage and supply/demand data.
    """

    # Map areas to endpoints (TEPCO example)
    # Note: Each power company has different URL structures.
    # We will focus on TEPCO for this MVP.

    if area.lower() != "tokyo":
        raise ValueError(
            f"Unsupported area: {area}. Currently only 'tokyo' (TEPCO) is supported in this MVP script."
        )

    response = _download_tepco_csv()

    # TEPCO CSV encoding is Shift-JIS
    csv_data = response.content.decode('shift_jis', errors='replace')

    # Parse CSV
    # TEPCO CSV structure: DATE, TIME, USAGE(10MW)... headers are in Japanese.
    # 実ファイル (juyo-2025.csv) はタイトル行・空行・"DATE,TIME,実績(万kW)" の順。
    # 行数の固定 skip ではなく DATE で始まるヘッダ行を探す。
    lines = csv_data.splitlines()
    header_idx = next((i for i, line in enumerate(lines) if line.startswith("DATE,")), None)
    if header_idx is None:
        raise ValueError(f"TEPCO CSV header (DATE,...) not found. First lines: {lines[:3]}")
    df = pl.read_csv("\n".join(lines[header_idx:]).encode("utf-8"))

    # Filter by date if specified
    if date:
        # TEPCO date format is usually YYYY/M/D
        # Assuming first column is DATE
        date_col = df.columns[0]
        df = df.with_columns(pl.col(date_col).str.to_date("%Y/%m/%d"))

        target_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()  # noqa: DTZ007
        df = df.filter(pl.col(date_col) == target_date)

        if df.is_empty():
            print(f"No data found for date: {date}")
            return df

    save_output(df, output_file)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Electric Power Usage (TEPCO).")
    parser.add_argument("--area", default="tokyo", help="Power Area (currently only 'tokyo' supported)")  # noqa: E501
    parser.add_argument("--date", help="Specific Date (YYYY-MM-DD). If omitted, fetches full year data.")  # noqa: E501
    parser.add_argument("--out", help="Output CSV filename (default: power_<area>.csv)")

    args = parser.parse_args()
    fetch_power_usage(args.area, args.date, args.out or f"power_{args.area}.csv")


if __name__ == "__main__":
    cli_entry(main)
