import argparse
from io import StringIO

import polars as pl
import requests  # noqa: F401 - テストが <module>.requests.get を patch する
from dotenv import load_dotenv

from api_utils import cli_entry, redact, require_api_key, save_output
from api_utils import get_with_retry_redacted as _get_redacted

load_dotenv()

BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

# 衛星センサー
SOURCES = {
    "modis":    "MODIS_NRT",       # MODIS (Terra/Aqua)
    "viirs_s":  "VIIRS_SNPP_NRT",  # VIIRS (Suomi NPP)
    "viirs_n":  "VIIRS_NOAA20_NRT",  # VIIRS (NOAA-20)
    "landsat":  "LANDSAT_NRT",     # LANDSAT
}

# 主要リスクエリア bbox (W, S, E, N)
RISK_REGIONS = {
    "us_west":     "-125,32,-114,49",     # 米西海岸（カリフォルニア・オレゴン・ワシントン）
    "california":  "-124,32,-114,42",
    "australia":   "112,-44,154,-10",     # オーストラリア全域
    "amazon":      "-74,-17,-43,5",       # アマゾン流域
    "siberia":     "60,50,180,75",        # シベリア
    "mediterranean": "-10,35,45,47",      # 地中海
    "southeast_asia": "95,-10,141,22",    # 東南アジア
    "japan":       "123,24,146,46",
}


def fetch_firms_data(
    region: str = "us_west",
    source: str = "viirs_n",
    day_range: int = 5,
    output_file: str | None = None,
) -> pl.DataFrame:
    """
    NASA FIRMS から山火事リアルタイム衛星データを取得するわ。
    無料APIキー: https://firms.modaps.eosdis.nasa.gov/api/map_key/
    - region: 事前定義リスクエリア / または bbox 'W,S,E,N' を直接指定
    - source: 'modis', 'viirs_s', 'viirs_n', 'landsat'
    - day_range: 過去 N 日 (1-5。FIRMS Area API の DAY_RANGE 仕様)
    """
    api_key = require_api_key(
        "NASA_FIRMS_API_KEY", "NASA FIRMS",
        "https://firms.modaps.eosdis.nasa.gov/api/map_key/"
    )

    bbox = RISK_REGIONS.get(region.lower(), region)
    sensor = SOURCES.get(source.lower(), source)

    if not 1 <= day_range <= 5:
        raise ValueError(f"day_range must be 1..5 (FIRMS Area API), got {day_range}")

    url = f"{BASE_URL}/{api_key}/{sensor}/{bbox}/{day_range}"

    print(f"Fetching NASA FIRMS: region={region}, sensor={sensor}, days={day_range}...")
    # MAP_KEY が URL パスに入るため、例外メッセージからは伏せる
    response = _get_redacted(url, [api_key], timeout=120)

    # 正常応答は latitude 列で始まる CSV。それ以外（"Invalid MAP_KEY." や
    # "Exceeding allowed transaction limit." 等のエラー文・空ボディ）は HTTP 200 でも失敗とする。
    text = response.text
    header = text.lstrip().split("\n", 1)[0]
    if "latitude" not in header:
        raise RuntimeError(f"FIRMS API error: {redact(text[:200], [api_key]) or '(empty response)'}")

    df = pl.read_csv(StringIO(text))

    if df.is_empty():
        print("No fire hotspots detected.")
        return df

    # 標準化: 日付 + value（brightness or frp）
    if "acq_date" in df.columns:
        df = df.with_columns(pl.col("acq_date").alias("date"))
    if "frp" in df.columns:  # Fire Radiative Power (主要強度指標)
        df = df.with_columns(pl.col("frp").alias("value"))
    elif "bright_ti4" in df.columns:
        df = df.with_columns(pl.col("bright_ti4").alias("value"))

    df = df.with_columns(
        pl.lit(region).alias("region"),
        pl.lit(sensor).alias("sensor"),
    )

    save_output(df, output_file)

    print(f"[FIRMS] {df.height} fire hotspots detected in {region}.")
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch wildfire hotspots from NASA FIRMS.")
    parser.add_argument("--region", default="us_west", help=f"Region: {list(RISK_REGIONS.keys())} or bbox 'W,S,E,N'")
    parser.add_argument("--source", default="viirs_n", help=f"Sensor: {list(SOURCES.keys())}")
    parser.add_argument("--days", type=int, default=5, help="Days (1-5).")
    parser.add_argument("--out", help="Output CSV filename.")
    args = parser.parse_args()
    fetch_firms_data(
        region=args.region,
        source=args.source,
        day_range=args.days,
        output_file=args.out,
    )


if __name__ == "__main__":
    cli_entry(main)
