import argparse
from datetime import datetime, timedelta

import pandas as pd
import polars as pl
import yfinance as yf


def fetch_freight_data(tickers: str = "BDRY", start_date: str | None = None, end_date: str | None = None, output_file: str | None = None) -> pl.DataFrame:  # noqa: E501
    """
    海運・物流コストの先行指標（ETFや関連株）を取得するわ。
    BDRY (Breakwave Dry Bulk Shipping ETF) はバルチック海運指数に近い動きをするの。
    """
    if not start_date:
        start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')  # noqa: DTZ005
    if not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')  # noqa: DTZ005

    print(f"Fetching Freight proxy data ({tickers}) from {start_date} to {end_date}...")

    ticker_list = [t.strip() for t in tickers.split(",")]

    try:
        # yfinance でデータ取得
        data = yf.download(ticker_list, start=start_date, end=end_date, interval="1d", auto_adjust=True)  # noqa: E501

        if data.empty:
            print("No data found.")
            return pl.DataFrame()

        # MultiIndexのフラット化処理
        if isinstance(data.columns, pd.MultiIndex):
            data = data.stack(level=1).reset_index() # yfinanceのバージョンによる違い吸収  # noqa: E501
            if 'level_1' in data.columns:
                 data.rename(columns={'level_1': 'Ticker'}, inplace=True)
            elif 'Ticker' not in data.columns: # fallback
                 # 如果 stack 结果不对，尝试另一种方式
                 data = data.stack().reset_index()
                 data.rename(columns={'level_1': 'Ticker'}, inplace=True)
        else:
            data = data.reset_index()
            data['Ticker'] = ticker_list[0]

        # 日付列の名前を統一
        if 'Date' in data.columns:
            data['Date'] = pd.to_datetime(data['Date']).dt.strftime('%Y-%m-%d')

        # 欠損値の削除
        data = data.dropna(subset=['Close'])

        # Polars に変換
        df = pl.from_pandas(data)

        if output_file:
            print(f"Saving to {output_file}...")
            df.write_csv(output_file)

        return df  # noqa: TRY300

    except Exception as e:  # noqa: BLE001
        print(f"Error fetching freight data: {e}")
        return pl.DataFrame()

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Freight & Logistics cost proxy data.")  # noqa: E501
    parser.add_argument("--tickers", default="BDRY", help="Comma-separated tickers (e.g., BDRY, ZIM, SBLK). Default: BDRY")  # noqa: E501
    parser.add_argument("--start", help="Start date (YYYY-MM-DD).")
    parser.add_argument("--end", help="End date (YYYY-MM-DD).")
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    fetch_freight_data(args.tickers, args.start, args.end, args.out)

if __name__ == "__main__":
    main()
