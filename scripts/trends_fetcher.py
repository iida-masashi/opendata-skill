import argparse

import pandas as pd
import polars as pl
import requests
from api_utils import cli_entry, retry_with_ratelimit, save_output
from pytrends.exceptions import ResponseError
from pytrends.request import TrendReq


@retry_with_ratelimit
def _interest_over_time(keywords: list[str], timeframe: str, geo: str) -> pd.DataFrame:
    # pytrends 内蔵リトライ（retries/backoff_factor>0）は urllib3 2.x で削除された
    # method_whitelist を渡して TypeError になるため使わず、共通の retry_with_ratelimit に任せる。
    # pytrends の ResponseError は requests の HTTPError に載せ替え、429/5xx だけ再試行させる。
    pytrends = TrendReq(hl='ja-JP', tz=540) # Japan timezone
    try:
        pytrends.build_payload(keywords, cat=0, timeframe=timeframe, geo=geo, gprop='')
        return pytrends.interest_over_time()
    except ResponseError as e:
        raise requests.exceptions.HTTPError(str(e), response=e.response) from e


def fetch_google_trends(
    keywords: str | list[str],
    timeframe: str = "today 5-y",
    geo: str = "JP",
    output_file: str | None = None,
) -> pl.DataFrame:
    """
    Fetches Google Trends data.
    - geo: 国コード ('JP', 'US', ...)。全世界は '' （'world' も '' として扱う）。
    - isPartial=True の行（集計途中の最新期間）は値が確定していないため落とす。
    """

    # Process keywords
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(',')]

    # pytrends の全世界指定は geo=''（'world' をそのまま送ると Google 側で国コードとして解釈されない）
    if geo.lower() == "world":
        geo = ""

    print(f"Fetching Google Trends for: {keywords} (Geo: {geo or 'worldwide'}, Timeframe: {timeframe})...")

    df = _interest_over_time(keywords, timeframe, geo)

    if df.empty:
        print("No data found.")
        return pl.DataFrame()

    # 不完全期間の行を落としてから 'isPartial' 列を削除
    if 'isPartial' in df.columns:
        df = df[~df['isPartial'].astype(bool)]
        df = df.drop(columns=['isPartial'])

    # インデックスを 'date' 列にして変換する。pandas 3 の pytrends は datetime64[s] を返し、
    # pl.from_pandas は pyarrow 無しだとこれを変換できないため列ごとに numpy 経由で組み立てる。
    date = pl.Series("date", df.index.to_numpy().astype("datetime64[us]"))
    df_polars = pl.DataFrame({str(c): df[c].to_numpy() for c in df.columns}).insert_column(0, date)

    save_output(df_polars, output_file)
    return df_polars

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Google Trends Data.")
    parser.add_argument("--keywords", required=True, help="Keywords (comma-separated). e.g., 'Python, Java, Rust'")
    parser.add_argument("--geo", default="JP", help="Geo Code (e.g., 'JP', 'US'). Use '' or 'world' for worldwide. Default: 'JP'")
    parser.add_argument("--timeframe", default="today 5-y", help="Timeframe (e.g., 'today 12-m', 'today 5-y', '2020-01-01 2023-12-31'). Default: 'today 5-y'")
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    output_file = args.out
    if not output_file:
        kw_str = "_".join(k.strip() for k in args.keywords.split(',')[:2])
        output_file = f"trends_{kw_str}.csv"
    fetch_google_trends(args.keywords, args.timeframe, args.geo, output_file)

if __name__ == "__main__":
    cli_entry(main)
