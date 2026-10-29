import argparse

import polars as pl
import requests
from api_utils import (
    cli_entry,
    default_date_range,
    require_api_key,
    save_output,
)
from api_utils import get_with_retry_redacted as _get_redacted
from dotenv import load_dotenv

load_dotenv()

# 需要予測・S&OP・与信管理向けの信用スプレッド・金融ストレス指標プリセット（FRED 公式系列）
CREDIT_STRESS_SERIES: dict[str, str] = {
    "hy_spread": "BAMLH0A0HYM2",        # 米ハイイールド債オプション調整後スプレッド OAS (ICE BofA, 日次)
    "ig_spread": "BAMLC0A0CM",          # 米投資適格社債スプレッド OAS (ICE BofA, 日次)
    "bbb_spread": "BAMLC0A4CBBB",       # 米BBB格社債スプレッド OAS (ICE BofA, 日次)
    "yield_curve_10y2y": "T10Y2Y",      # 米国債 10年-2年 長短金利差 (FRB, 日次)
    "yield_curve_10y3m": "T10Y3M",      # 米国債 10年-3ヶ月 長短金利差 (FRB, 日次)
    "real_rate_10y": "DFII10",          # 米国10年実質金利・TIPS利回り (FRB, 日次)
    "breakeven_10y": "T10YIE",          # 米国10年期待インフレ率 (FRB, 日次)
    "vix": "VIXCLS",                    # CBOE VIX ボラティリティ指数 (CBOE, 日次)
    "stl_fsi": "STLFSI4",               # セントルイス連銀 金融ストレス指数 (週次)
    "chicago_nfci": "NFCI",             # シカゴ連銀 全米金融環境指数 (週次)
}


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


def fetch_credit_spread(
    series: str = "hy_spread",
    start_date: str | None = None,
    end_date: str | None = None,
    output_file: str | None = None,
) -> pl.DataFrame:
    """
    FRED 経由で信用スプレッド・長短金利差・実質金利・金融ストレス指標を取得する。
    series の例:
    - 'hy_spread': 米ハイイールド債スプレッド OAS (BAMLH0A0HYM2)
    - 'ig_spread': 米投資適格社債スプレッド OAS (BAMLC0A0CM)
    - 'yield_curve_10y2y': 米国債 10年-2年 長短金利差 (T10Y2Y)
    - 'real_rate_10y': 米国10年実質金利 (DFII10)
    - 'vix': CBOE VIX 指数 (VIXCLS)
    - 'stl_fsi': セントルイス連銀 金融ストレス指数 (STLFSI4)
    """
    return fetch_fred_alias(CREDIT_STRESS_SERIES, series, start_date, end_date, output_file)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Macroeconomic & Credit Stress data from FRED API.")
    parser.add_argument(
        "--series",
        required=True,
        help=f"FRED Series ID (e.g., UNRATE) or credit alias {list(CREDIT_STRESS_SERIES.keys())}.",
    )
    parser.add_argument("--start", help="Start date (YYYY-MM-DD).")
    parser.add_argument("--end", help="End date (YYYY-MM-DD).")
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    if args.series.lower() in CREDIT_STRESS_SERIES:
        fetch_credit_spread(args.series, args.start, args.end, args.out)
    else:
        fetch_fred_data(args.series, args.start, args.end, args.out)

if __name__ == "__main__":
    cli_entry(main)
