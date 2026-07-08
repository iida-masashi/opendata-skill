import argparse

import polars as pl
from dotenv import load_dotenv

try:
    from fred_fetcher import fetch_fred_data
except ImportError:
    from .fred_fetcher import fetch_fred_data

load_dotenv()

# FRED経由で取得可能なPMI系列 (ISM発表値・S&P Global PMI)
PMI_SERIES = {
    # --- ISM (米国) ---
    "ism_mfg": "MANEMP",            # Fallback: 製造業雇用 (ISM PMIはFREDでは直接公開制限あり)
    "ism_mfg_pmi": "NAPM",          # ISM Manufacturing PMI (旧ID / 廃止の可能性あり)
    "ism_services": "NMFCI",        # Services index proxy
    # --- S&P Global / Markit ---
    "us_mfg_pmi": "IPMAN",          # Industrial Production: Manufacturing (強い代替指標)
    "us_new_orders": "AMTMNO",      # 製造業新規受注 (PMI新規受注と高相関)
    "us_inventories": "AMTMTI",     # 製造業在庫
    "us_capacity_util": "MCUMFN",   # 製造業稼働率
    # --- グローバル ---
    "global_econ_policy_uncertainty": "GEPUCURRENT",  # 経済政策不確実性指数
    "oecd_cli_us": "USALOLITONOSTSAM",  # OECD景気先行指数 (米)
    "oecd_cli_jp": "JPNLOLITONOSTSAM",  # OECD景気先行指数 (日)
    "oecd_cli_cn": "CHNLOLITONOSTSAM",  # OECD景気先行指数 (中)
    "oecd_cli_eu": "EA19LOLITONOSTSAM", # OECD景気先行指数 (ユーロ圏)
}


def fetch_pmi_data(
    series: str = "us_new_orders",
    start_date: str | None = None,
    end_date: str | None = None,
    output_file: str | None = None,
) -> pl.DataFrame:
    """
    PMI および関連する製造業先行指標を FRED 経由で取得するわ。
    ISM の完全なPMI系列はライセンス制約があるため、FREDで公開されている代替・関連指標を活用。
    - 'us_new_orders': 製造業新規受注 (PMI新規受注サブインデックスと高相関)
    - 'oecd_cli_us': 米国OECD景気先行指数 (製造業PMIの先行指標として標準)
    - 'global_econ_policy_uncertainty': 経済政策不確実性指数
    """
    series_id = PMI_SERIES.get(series.lower(), series)

    df = fetch_fred_data(
        series_id=series_id,
        start_date=start_date,
        end_date=end_date,
        output_file=None,  # FRED側で書かず、ここでsereis aliasを付与してから書く
    )
    if df.is_empty():
        return df

    df = df.with_columns(pl.lit(series).alias("series"))

    if output_file:
        print(f"Saving to {output_file}...")
        df.write_csv(output_file)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch PMI and manufacturing leading indicators.")
    parser.add_argument("--series", default="us_new_orders", help=f"Series alias or FRED ID. Aliases: {list(PMI_SERIES.keys())}")
    parser.add_argument("--start", help="Start date (YYYY-MM-DD).")
    parser.add_argument("--end", help="End date (YYYY-MM-DD).")
    parser.add_argument("--out", help="Output CSV filename.")
    args = parser.parse_args()
    fetch_pmi_data(args.series, args.start, args.end, args.out)


if __name__ == "__main__":
    main()
