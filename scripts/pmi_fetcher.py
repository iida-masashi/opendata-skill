import argparse

import polars as pl
from dotenv import load_dotenv

from api_utils import cli_entry
from fred_fetcher import fetch_fred_alias

load_dotenv()

# FRED経由で取得可能なPMI関連・製造業先行指標。
# ISM の PMI 系列は 2016-06-24 に FRED から全22系列が削除されており、FRED では取得できない
# (https://news.research.stlouisfed.org/2016/06/institute-for-supply-management-data-to-be-removed-from-fred/)。
# S&P Global PMI も FRED には無い。以下の "pmi" を名乗るエイリアスは PMI そのものではない。
PMI_SERIES = {
    # --- ISM (米国) ---
    "ism_mfg": "MANEMP",            # PMIではない: All Employees, Manufacturing (BLS 製造業雇用者数, 千人)
    "ism_mfg_pmi": "NAPM",          # FREDから削除済み (ISM Manufacturing PMI)。取得はエラーになる
    "ism_services": "NMFCI",        # FREDから削除済み (ISM Non-Manufacturing)。取得はエラーになる
    # --- 製造業の代替指標 ---
    "us_mfg_pmi": "IPMAN",          # PMIではない: Industrial Production: Manufacturing (NAICS) (FRB G.17 生産指数)
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
    return fetch_fred_alias(PMI_SERIES, series, start_date, end_date, output_file)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch PMI and manufacturing leading indicators.")
    parser.add_argument("--series", default="us_new_orders", help=f"Series alias or FRED ID. Aliases: {list(PMI_SERIES.keys())}")
    parser.add_argument("--start", help="Start date (YYYY-MM-DD).")
    parser.add_argument("--end", help="End date (YYYY-MM-DD).")
    parser.add_argument("--out", help="Output CSV filename.")
    args = parser.parse_args()
    fetch_pmi_data(args.series, args.start, args.end, args.out)


if __name__ == "__main__":
    cli_entry(main)
