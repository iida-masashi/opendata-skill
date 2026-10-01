import argparse

import polars as pl
from api_utils import cli_entry, save_output
from yahoo_fetcher import fetch_yahoo_finance


def fetch_freight_data(tickers: str = "BDRY", start_date: str | None = None, end_date: str | None = None, output_file: str | None = None) -> pl.DataFrame:
    """
    海運・物流コストの先行指標（ETFや関連株）を取得するわ。
    BDRY (Breakwave Dry Bulk Shipping ETF) はバルチック海運指数に近い動きをするの。
    tickers はカンマ区切り・スペース区切りどちらでもよい（取得は yahoo_fetcher に委譲）。
    """
    print(f"Fetching Freight proxy data ({tickers})...")

    data = fetch_yahoo_finance(tickers, start_date=start_date, end_date=end_date, interval="1d")

    # 従来の出力スキーマ（Date 文字列 / Ticker / Close / High / Low / Open / Volume）に合わせる
    df = data.rename({"date": "Date", "value": "Close"}).with_columns(
        pl.col("Date").dt.strftime("%Y-%m-%d")
    )
    df = df.filter(pl.col("Close").is_not_null())
    lead = [c for c in ("Date", "Ticker", "Close") if c in df.columns]
    df = df.select(lead + [c for c in df.columns if c not in lead])

    save_output(df, output_file)
    return df

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Freight & Logistics cost proxy data.")
    parser.add_argument("--tickers", default="BDRY", help="Comma- or space-separated tickers (e.g., BDRY, ZIM, SBLK). Default: BDRY")
    parser.add_argument("--start", help="Start date (YYYY-MM-DD).")
    parser.add_argument("--end", help="End date (YYYY-MM-DD).")
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    fetch_freight_data(args.tickers, args.start, args.end, args.out)

if __name__ == "__main__":
    cli_entry(main)
