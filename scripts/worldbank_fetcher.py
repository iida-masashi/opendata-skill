import argparse

import polars as pl
import wbgapi as wb

from api_utils import cli_entry, save_output

# Common Indicator Aliases for Easy Access
INDICATORS = {
    "gdp": "NY.GDP.MKTP.CD",       # GDP (current US$)
    "gdp_growth": "NY.GDP.MKTP.KD.ZG", # GDP growth (annual %)
    "gni": "NY.GNP.MKTP.CD",       # GNI (current US$)
    "population": "SP.POP.TOTL",   # Population, total
    "inflation": "FP.CPI.TOTL.ZG", # Inflation, consumer prices (annual %)
    "unemployment": "SL.UEM.TOTL.ZS", # Unemployment, total (% of total labor force)
    "co2": "EN.ATM.CO2E.PC",       # CO2 emissions (metric tons per capita)
    "poverty": "SI.POV.DDAY",      # Poverty headcount ratio at $2.15 a day
    "life_expectancy": "SP.DYN.LE00.IN" # Life expectancy at birth, total
}

def fetch_worldbank_data(
    indicators: str | list[str],
    countries: str | list[str] = "all",
    start_year: str | int | None = None,
    end_year: str | int | None = None,
    output_file: str | None = None,
) -> pl.DataFrame:
    """
    Fetches data from World Bank API using wbgapi.
    Covers General Stats (GDP, Pop) and SDGs.
    戻り値は国 × 年 (YR2020, YR2021, ...) のワイド形式。output_file を指定すると CSV にも保存する。
    """

    # Process indicators
    if isinstance(indicators, str):
        raw_inds = [i.strip() for i in indicators.split(',')]
    else:
        raw_inds = indicators

    final_inds = []
    for i in raw_inds:
        if i.lower() in INDICATORS:
            print(f"Using alias: {i} -> {INDICATORS[i.lower()]}")
            final_inds.append(INDICATORS[i.lower()])
        else:
            final_inds.append(i)
    indicators = final_inds

    # Process countries
    if countries != 'all' and isinstance(countries, str):
        countries = [c.strip() for c in countries.split(',')]

    print(f"Fetching World Bank Data for indicators: {indicators}...")
    print(f"Countries: {countries}")

    # Determine time range. A partial range (only one of start/end) must be
    # honored, not silently widened to 'all'. World Bank series start ~1960;
    # there is no future data, so an open upper bound is clamped to the data.
    if start_year or end_year:
        lo = int(start_year) if start_year else 1960
        hi = int(end_year) if end_year else 2100
        time_range = range(lo, hi + 1)
    else:
        time_range = 'all'

    # Fetching
    # labels=True adds Country Name column.
    pdf = wb.data.DataFrame(indicators, economy=countries, time=time_range, labels=True)  # noqa: E501

    # Reset index to make Economy (Country Code) a column
    pdf.reset_index(inplace=True)

    if pdf.empty:
        print("No data found.")
        return pl.DataFrame()

    # pyarrow 非依存で変換する（pl.from_pandas は文字列列に pyarrow を要する）。NaN は null にそろえる。
    df = pl.DataFrame(pdf.to_dict(orient="list")).fill_nan(None)

    save_output(df, output_file)
    return df


def _default_output_file(indicators: str) -> str:
    """CLI 用の既定出力ファイル名（エイリアス名から作る）。"""
    codes = {INDICATORS.get(i.strip().lower(), i.strip()) for i in indicators.split(',')}
    safe_inds = "_".join([k for k, v in INDICATORS.items() if v in codes][:3])
    if not safe_inds:
        safe_inds = "custom_indicators"
    return f"wb_{safe_inds}.csv"

def search_indicators(query: str) -> None:
    """
    Searches for indicators matching the query.
    """
    print(f"Searching for indicators matching '{query}'...")
    wb.series.info(q=query)

def list_aliases() -> None:
    print("Available Metric Aliases:")
    for alias, code in INDICATORS.items():
        print(f"  {alias.ljust(15)} : {code}")

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch World Bank / SDG Data.")
    parser.add_argument("--indicators", help="Indicator Codes or Aliases (comma-separated). e.g., 'gdp,population' or 'NY.GDP.MKTP.CD'")  # noqa: E501
    parser.add_argument("--countries", default="all", help="Country Codes (ISO3, comma-separated). Default: 'all'. e.g., 'JPN,USA,CHN,WLD'")  # noqa: E501
    parser.add_argument("--start", type=int, help="Start Year (YYYY)")
    parser.add_argument("--end", type=int, help="End Year (YYYY)")
    parser.add_argument("--search", help="Search term for indicators. If set, only searches and exits.")  # noqa: E501
    parser.add_argument("--list", action="store_true", help="List available metric aliases")  # noqa: E501
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()

    if args.list:
        list_aliases()
    elif args.search:
        search_indicators(args.search)
    elif args.indicators:
        fetch_worldbank_data(args.indicators, args.countries, args.start, args.end,
                             args.out or _default_output_file(args.indicators))
    else:
        parser.error("One of --indicators, --search, or --list is required.")


if __name__ == "__main__":
    cli_entry(main)
