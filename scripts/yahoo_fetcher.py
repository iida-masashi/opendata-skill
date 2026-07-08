import argparse
from datetime import datetime, timedelta

import polars as pl
import yfinance as yf


def fetch_yahoo_finance(
    tickers: str,
    start_date: str | None = None,
    end_date: str | None = None,
    interval: str = "1d",
    output_file: str | None = None,
) -> pl.DataFrame | None:
    """
    Fetches historical data for given tickers from Yahoo Finance.
    """
    if not start_date:
        start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')  # noqa: DTZ005
    if not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')  # noqa: DTZ005

    print(f"Fetching Yahoo Finance data for {tickers} from {start_date} to {end_date}...")  # noqa: E501

    # yfinance automatically handles multiple tickers and returns a pandas DataFrame
    try:
        df = yf.download(tickers, start=start_date, end=end_date, interval=interval, group_by='ticker', auto_adjust=True)  # noqa: E501

        if df.empty:
            print("No data found for the given tickers.")
            return None

        # Check if LITH=F was requested but returned empty/failed
        # Using pandas-style access on the initial df (still a pandas object here)
        is_lith_missing = False
        if "LITH=F" in tickers:
            if hasattr(df.columns, 'levels'): # MultiIndex
                if "LITH=F" not in df.columns.levels[0]:
                    is_lith_missing = True
                elif df["LITH=F"].isnull().all().all():
                    is_lith_missing = True
            else: # Single Index
                if "LITH=F" not in df.columns or df["LITH=F"].isnull().all():
                    is_lith_missing = True

        if is_lith_missing:
            print("Warning: LITH=F data not found. Attempting fallback to LIT (Global X Lithium & Battery Tech ETF)...")  # noqa: E501
            try:
                lit_df = yf.download("LIT", start=start_date, end=end_date, interval=interval, auto_adjust=True)  # noqa: E501
                if not lit_df.empty:
                    # If single ticker request failed, we can just replace
                    if not hasattr(df.columns, 'levels'):
                        df = lit_df
                        tickers = "LIT"
                    # For MultiIndex, we'll handle merging later in Polars
            except Exception as e:  # noqa: BLE001
                print(f"Fallback to LIT failed: {e}")

        # Flatten MultiIndex columns or handle single ticker
        if hasattr(df.columns, 'levels'):
            if len(df.columns.levels[0]) > 1:
                # Multiple tickers: Stack
                df = df.stack(level=0)
                df.reset_index(inplace=True)
                # Convert to Polars as requested
                data = pl.from_pandas(df)
                # Standardize column names
                rename_map = {'Date': 'date', 'level_1': 'Ticker', 'Close': 'value'}
                data = data.rename({k: v for k, v in rename_map.items() if k in data.columns})
                # If 'value' is still not there, try whatever was in the MultiIndex
                if 'value' not in data.columns and len(data.columns) > 2:
                    data = data.rename({data.columns[2]: 'value'})
            else:
                # Single ticker but MultiIndex
                ticker_name = df.columns.levels[0][0]
                price_col = 'Close' if 'Close' in df.columns.levels[1] else df.columns.levels[1][0]
                df_single = df[ticker_name].copy()
                df_single.reset_index(inplace=True)
                data = pl.from_pandas(df_single)
                data = data.rename({'Date': 'date', price_col: 'value'})
                data = data.with_columns(pl.lit(ticker_name).alias('Ticker'))
        else:
            # Single ticker flat
            df.reset_index(inplace=True)
            data = pl.from_pandas(df)
            data = data.rename({'Date': 'date', 'Close': 'value'})
            data = data.with_columns(pl.lit(tickers.strip()).alias('Ticker'))

    except Exception as e:  # noqa: BLE001
        print(f"Error fetching data: {e}")
        return None

    if data.is_empty():
        print("No data found for the given tickers.")
        return None

    # Final cleanup to ensure lowercase 'date'
    data = data.rename({c: c.lower() for c in data.columns if c.lower() == 'date'})

    # If we have fallback data for LIT and it wasn't in the original download (mixed case)
    if "LITH=F" in tickers and "LIT" not in data['Ticker'].unique().to_list():
         try:
            lit_df = yf.download("LIT", start=start_date, end=end_date, interval=interval, auto_adjust=True)
            if not lit_df.empty:
                lit_df.reset_index(inplace=True)
                lit_pl = pl.from_pandas(lit_df)
                lit_pl = lit_pl.with_columns(pl.lit('LIT').alias('Ticker'))
                lit_pl = lit_pl.rename({'Date': 'date', 'Close': 'value'})
                lit_pl = lit_pl.rename({c: c.lower() for c in lit_pl.columns if c.lower() == 'date'})

                # Align columns and concat using Polars
                common_cols = [c for c in data.columns if c in lit_pl.columns]
                data = pl.concat([data.select(common_cols), lit_pl.select(common_cols)])
                print("Merged LIT data.")
         except Exception:  # noqa: S110
             pass

    # Output filename
    if not output_file:
        safe_tickers = tickers.replace(' ', '_').replace('^', '').replace('=', '')
        output_file = f"yahoo_{safe_tickers}_{start_date}_{end_date}.csv"

    print(f"Saving to {output_file}...")
    try:
        data.write_csv(output_file)
    except Exception as e:  # noqa: BLE001
        print(f"Error saving CSV: {e}")

    print("Done.")
    return data

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch historical market data from Yahoo Finance.")  # noqa: E501
    parser.add_argument("--tickers", required=True, help="Space-separated list of tickers. Examples: '7203.T' (Toyota), 'USDJPY=X' (FX), 'CL=F' (Oil), 'GC=F' (Gold)")  # noqa: E501
    parser.add_argument("--start", help="Start date (YYYY-MM-DD). Default: 1 year ago.")
    parser.add_argument("--end", help="End date (YYYY-MM-DD). Default: Today.")
    parser.add_argument("--interval", default="1d", help="Data interval (1d, 1wk, 1mo, 1h, etc.). Default: 1d.")  # noqa: E501
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    fetch_yahoo_finance(args.tickers, args.start, args.end, args.interval, args.out)

if __name__ == "__main__":
    main()
