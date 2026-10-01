import argparse
from datetime import UTC, datetime

import polars as pl
import requests  # noqa: F401 - テストが <module>.requests.get を patch する
from dotenv import load_dotenv

from api_utils import cli_entry, redact, require_api_key, save_output
from api_utils import get_with_retry as _get_with_retry
from api_utils import get_with_retry_redacted as _get_redacted

load_dotenv()

# USDA Quick Stats API (要APIキー)
USDA_QS = "https://quickstats.nass.usda.gov/api/api_GET"
# FAOSTAT API (無料・APIキー不要)
FAOSTAT_BASE = "https://fenixservices.fao.org/faostat/api/v1/en"

# 主要商品エイリアス
USDA_COMMODITY_ALIAS = {
    "corn": "CORN",
    "wheat": "WHEAT",
    "soybean": "SOYBEANS",
    "rice": "RICE",
    "cotton": "COTTON",
    "beef": "CATTLE",
    "pork": "HOGS",
    "milk": "MILK",
}

# FAOSTAT ドメインエイリアス
FAOSTAT_DOMAIN = {
    "production": "QCL",        # Crops and livestock products
    "trade": "TCL",             # Trade - Crops and livestock products
    "food_balance": "FBS",      # Food Balance Sheets
    "prices": "PP",             # Producer Prices
    "food_security": "FS",      # Suite of Food Security Indicators
}

SOURCES = ("usda", "faostat")



def fetch_usda_quickstats(
    commodity: str,
    year: str | None = None,
    state: str = "US TOTAL",
    statistic: str = "PRODUCTION",
) -> pl.DataFrame:
    """USDA NASS Quick Stats から米国農業統計を取得"""
    api_key = require_api_key("USDA_API_KEY", "USDA NASS", "https://quickstats.nass.usda.gov/api")

    comm = USDA_COMMODITY_ALIAS.get(commodity.lower(), commodity.upper())
    if not year:
        year = str(datetime.now(UTC).year - 1)

    params = {
        "key": api_key,
        "commodity_desc": comm,
        "year": year,
        "state_name": state,
        "statisticcat_desc": statistic,
        "format": "JSON",
    }

    response = _get_redacted(USDA_QS, [api_key], params=params)
    data = response.json()
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(f"USDA QuickStats API error: {redact(str(data['error']), [api_key])}")
    rows = data.get("data", [])
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows)


def fetch_faostat(
    domain: str = "production",
    area: str = "all",
    item: str = "all",
    year: str = "2020,2021,2022,2023",
    element: str | None = None,
) -> pl.DataFrame:
    """FAOSTAT から国際農業統計を取得（APIキー不要）"""
    dom = FAOSTAT_DOMAIN.get(domain.lower(), domain.upper())
    url = f"{FAOSTAT_BASE}/data/{dom}"

    params = {
        "area": area,
        "item": item,
        "year": year,
        "output_type": "json",
    }
    if element:
        params["element"] = element

    response = _get_with_retry(url, params=params, timeout=120)
    data = response.json()
    rows = data.get("data", [])
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows)


def fetch_agri_data(
    source: str = "faostat",
    commodity: str = "corn",
    year: str | None = None,
    area: str = "all",
    domain: str = "production",
    output_file: str | None = None,
) -> pl.DataFrame:
    """
    USDA / FAO から農業・食品データを取得するわ。
    - source: 'usda' (米国詳細) / 'faostat' (グローバル)
    - commodity: 'corn', 'wheat', 'soybean', 'rice', 'cotton' etc.
    """
    if source.lower() not in SOURCES:
        raise ValueError(f"Unknown source: {source}. Available: {list(SOURCES)}")

    print(f"Fetching agricultural data: source={source}, commodity={commodity}, area={area}...")
    if source.lower() == "usda":
        df = fetch_usda_quickstats(commodity=commodity, year=year)
    else:
        # FAOSTATではitem名を英語で渡す必要があるが、ALLを許容
        item_code = commodity if commodity != "all" else "all"
        df = fetch_faostat(
            domain=domain,
            area=area,
            item=item_code,
            year=year or "2020,2021,2022,2023",
        )

    if df.is_empty():
        print("No agricultural data found.")
        return df

    save_output(df, output_file)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch USDA / FAOSTAT agricultural data.")
    parser.add_argument("--source", default="faostat", choices=["usda", "faostat"])
    parser.add_argument("--commodity", default="corn", help="Commodity name or USDA alias.")
    parser.add_argument("--year", help="Year (or comma-separated for FAOSTAT).")
    parser.add_argument("--area", default="all", help="Area/country code (FAOSTAT).")
    parser.add_argument("--domain", default="production", help=f"FAOSTAT domain: {list(FAOSTAT_DOMAIN.keys())}")
    parser.add_argument("--out", help="Output CSV filename.")
    args = parser.parse_args()
    fetch_agri_data(
        source=args.source,
        commodity=args.commodity,
        year=args.year,
        area=args.area,
        domain=args.domain,
        output_file=args.out,
    )


if __name__ == "__main__":
    cli_entry(main)
