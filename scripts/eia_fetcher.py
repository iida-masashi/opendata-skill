import argparse

import polars as pl
import requests  # noqa: F401 - テストが <module>.requests.get を patch する
from dotenv import load_dotenv

from api_utils import (
    cli_entry,
    default_date_range,
    redact,
    require_api_key,
    save_output,
)
from api_utils import get_with_retry_redacted as _get_redacted

load_dotenv()

# EIA API v2 Base URL
BASE_URL = "https://api.eia.gov/v2"

# 主要シリーズエイリアス (SCM需要予測に効く先行指標)
SERIES_ALIAS = {
    # --- 石油 ---
    "crude_stocks": "petroleum/stoc/wstk/data",           # 週次原油在庫
    "crude_production": "petroleum/crd/crpdn/data",       # 原油生産量
    "gasoline_stocks": "petroleum/stoc/wstk/data",        # ガソリン在庫
    "wti_price": "petroleum/pri/spt/data",                # WTI現物価格
    "refinery_util": "petroleum/pnp/wiup/data",           # 精製所稼働率
    # --- 天然ガス ---
    "natgas_storage": "natural-gas/stor/wkly/data",       # 天然ガス週次在庫
    "natgas_price": "natural-gas/pri/fut/data",           # Henry Hub価格
    # --- 電力 ---
    "electricity_demand": "electricity/rto/region-data/data",  # 地域別電力需要
    "electricity_gen": "electricity/rto/fuel-type-data/data",  # 燃料別発電量
    # --- 国際 ---
    "intl_oil": "international/data",                     # 国際石油統計
}

# 同一エンドポイント (petroleum/stoc/wstk) を共有するシリーズの製品識別ファセット。
# これが無いと crude_stocks と gasoline_stocks が同一の混合データを返してしまう。
SERIES_DEFAULT_FACETS = {
    "crude_stocks": {"series": "WCESTUS1"},      # 原油在庫 (Crude Oil Ending Stocks)
    "gasoline_stocks": {"series": "WGTSTUS1"},   # 総自動車ガソリン在庫
}



def fetch_eia_data(
    series: str = "crude_stocks",
    start_date: str | None = None,
    end_date: str | None = None,
    frequency: str = "weekly",
    facets: dict[str, str] | None = None,
    output_file: str | None = None,
) -> pl.DataFrame:
    """
    EIA (米エネルギー情報局) API v2 からエネルギー需給データを取得するわ。
    - 'crude_stocks': 週次原油在庫（精製マージンの先行指標）
    - 'natgas_storage': 天然ガス在庫（暖房需要・電力需要先行）
    - 'refinery_util': 精製所稼働率（供給タイト度）
    """
    api_key = require_api_key("EIA_API_KEY", "EIA", "https://www.eia.gov/opendata/register.php")

    endpoint = SERIES_ALIAS.get(series.lower(), series)
    url = f"{BASE_URL}/{endpoint}"

    # 呼び出し側がファセット未指定なら、共有エンドポイント用のデフォルト製品ファセットを補う
    if facets is None:
        facets = SERIES_DEFAULT_FACETS.get(series.lower())

    start_date, end_date = default_date_range(start_date, end_date, 365 * 3)

    params: dict = {
        "api_key": api_key,
        "frequency": frequency,
        "data[0]": "value",
        "start": start_date,
        "end": end_date,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": 5000,
    }
    if facets:
        for k, v in facets.items():
            params[f"facets[{k}][]"] = v

    print(f"Fetching EIA data: {series} ({endpoint}) from {start_date} to {end_date}...")
    response = _get_redacted(url, [api_key], params=params)
    data = response.json()
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(f"EIA API error: {redact(str(data['error']), [api_key])}")

    rows = data.get("response", {}).get("data", [])
    if not rows:
        print("No EIA data found.")
        return pl.DataFrame()

    df = pl.DataFrame(rows)

    # 標準化: period -> date, value数値化
    if "period" in df.columns:
        df = df.with_columns(pl.col("period").cast(pl.Utf8).alias("date"))
    if "value" in df.columns:
        df = df.with_columns(
            pl.col("value").cast(pl.Float64, strict=False).alias("value")
        )

    df = df.with_columns(pl.lit(series).alias("series_alias"))

    save_output(df, output_file)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch US Energy data from EIA API v2.")
    parser.add_argument("--series", default="crude_stocks", help=f"Series alias. Options: {list(SERIES_ALIAS.keys())}")
    parser.add_argument("--start", help="Start date (YYYY-MM-DD).")
    parser.add_argument("--end", help="End date (YYYY-MM-DD).")
    parser.add_argument("--freq", default="weekly", help="weekly/monthly/annual.")
    parser.add_argument("--out", help="Output CSV filename.")
    args = parser.parse_args()
    fetch_eia_data(
        series=args.series,
        start_date=args.start,
        end_date=args.end,
        frequency=args.freq,
        output_file=args.out,
    )


if __name__ == "__main__":
    cli_entry(main)
