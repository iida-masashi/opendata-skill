import argparse

import pandas as pd
import polars as pl
import yfinance as yf
from api_utils import cli_entry, default_date_range, save_output


def parse_tickers(tickers: str | list[str]) -> list[str]:
    """ティッカー指定をリストにする。スペース区切り・カンマ区切りの両方を受け付ける。"""
    if isinstance(tickers, str):
        return tickers.replace(",", " ").split()
    return [t.strip() for t in tickers if t.strip()]


def _frame_to_polars(pdf: pd.DataFrame) -> pl.DataFrame:
    """1ティッカー分の pandas DF（DatetimeIndex）を、インデックスを 'date' 列にして Polars に変換する。

    yfinance のインデックス名は日次 'Date'・日中足 'Datetime' と変わるので名前に依存しない。
    pyarrow 無しでも変換できるよう、列ごとに numpy 経由で組み立てる
    （tz付き日時は pl.from_pandas が pyarrow を要求するため UTC 経由でタイムゾーンを付け直す）。
    """
    idx = pdf.index
    if getattr(idx, "tz", None) is not None:
        date = (
            pl.Series("date", idx.tz_convert("UTC").tz_localize(None).to_numpy())
            .dt.replace_time_zone("UTC")
            .dt.convert_time_zone(str(idx.tz))
        )
    else:
        date = pl.Series("date", idx.to_numpy())
    data = pl.DataFrame({str(c): pdf[c].to_numpy() for c in pdf.columns}, nan_to_null=True)
    return data.insert_column(0, date)


def _download(
    ticker_list: list[str], start_date: str, end_date: str, interval: str
) -> pl.DataFrame:
    """yf.download を呼び、[date, 価格列..., Ticker] の縦持ち Polars DF にする（取得0件なら空DF）。"""
    df = yf.download(ticker_list, start=start_date, end=end_date, interval=interval, group_by='ticker', auto_adjust=True)
    if df is None or df.empty:
        return pl.DataFrame()

    if isinstance(df.columns, pd.MultiIndex):
        # group_by='ticker' なので level 0 がティッカー（yfinance 1.x は単一ティッカーでも MultiIndex）
        frames = [
            _frame_to_polars(df[t]).with_columns(pl.lit(str(t)).alias('Ticker'))
            for t in df.columns.get_level_values(0).unique()
        ]
        data = pl.concat(frames, how="diagonal_relaxed")
    else:
        data = _frame_to_polars(df).with_columns(pl.lit(ticker_list[0]).alias('Ticker'))

    # 複数ティッカーの取引カレンダー差で生じる全欠損行（そのティッカーには無い日時）を落とす
    price_cols = [c for c in data.columns if c not in ('date', 'Ticker')]
    if price_cols:
        data = data.filter(~pl.all_horizontal(pl.col(price_cols).is_null()))

    if 'Close' in data.columns:
        data = data.rename({'Close': 'value'})
    return data


def _is_all_missing(data: pl.DataFrame, ticker: str) -> bool:
    if data.is_empty() or 'Ticker' not in data.columns:
        return True
    return data.filter(pl.col('Ticker') == ticker).is_empty()


def fetch_yahoo_finance(
    tickers: str | list[str],
    start_date: str | None = None,
    end_date: str | None = None,
    interval: str = "1d",
    output_file: str | None = None,
) -> pl.DataFrame:
    """
    Fetches historical data for given tickers from Yahoo Finance.
    tickers はスペース区切り・カンマ区切りどちらでもよい。
    """
    start_date, end_date = default_date_range(start_date, end_date, days=365)
    ticker_list = parse_tickers(tickers)

    print(f"Fetching Yahoo Finance data for {ticker_list} from {start_date} to {end_date}...")

    data = _download(ticker_list, start_date, end_date, interval)

    # LITH=F が取れなかった場合は LIT (Global X Lithium & Battery Tech ETF) で補う
    if "LITH=F" in ticker_list and _is_all_missing(data, "LITH=F"):
        print("Warning: LITH=F data not found. Attempting fallback to LIT (Global X Lithium & Battery Tech ETF)...")
        lit = _download(["LIT"], start_date, end_date, interval)
        if lit.is_empty():
            print("Warning: fallback LIT data not found either.")
        elif data.is_empty():
            data = lit
        else:
            data = pl.concat([data, lit], how="diagonal_relaxed")
            print("Merged LIT data.")

    if data.is_empty():
        # yfinance は取得失敗（無効なティッカー・通信エラー）を例外にせず空DFで返すため、
        # 0件を「データ無し」と確定できない。失敗として扱う。
        raise RuntimeError(
            f"No data returned from Yahoo Finance for {ticker_list} "
            f"({start_date}→{end_date}, interval={interval}). "
            "Check the tickers / period (yfinance logs the per-ticker error)."
        )

    save_output(data, output_file)
    return data

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch historical market data from Yahoo Finance.")
    parser.add_argument("--tickers", required=True, nargs="+", help="Space- or comma-separated list of tickers. Examples: '7203.T' (Toyota), 'USDJPY=X' (FX), 'CL=F' (Oil), 'GC=F' (Gold)")
    parser.add_argument("--start", help="Start date (YYYY-MM-DD). Default: 1 year ago.")
    parser.add_argument("--end", help="End date (YYYY-MM-DD). Default: Today.")
    parser.add_argument("--interval", default="1d", help="Data interval (1d, 1wk, 1mo, 1h, etc.). Default: 1d.")
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    tickers = parse_tickers(" ".join(args.tickers))
    output_file = args.out
    if not output_file:
        start_date, end_date = default_date_range(args.start, args.end, days=365)
        safe_tickers = "_".join(tickers).replace('^', '').replace('=', '')
        output_file = f"yahoo_{safe_tickers}_{start_date}_{end_date}.csv"
    fetch_yahoo_finance(tickers, args.start, args.end, args.interval, output_file)

if __name__ == "__main__":
    cli_entry(main)
