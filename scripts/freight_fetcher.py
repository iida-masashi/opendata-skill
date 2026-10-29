import argparse

import polars as pl
from api_utils import cli_entry, save_output
from fred_fetcher import fetch_fred_alias
from yahoo_fetcher import fetch_yahoo_finance

# Yahoo Finance 経由で日次取得できる海運 ETF・船社バスケットのプリセット
FREIGHT_ETF_PRESETS: dict[str, str] = {
    "dry_bulk": "BDRY",                     # Breakwave Dry Bulk Shipping ETF (BDI 先物連動)
    "tanker": "BWET",                       # Breakwave Tanker Shipping ETF (原油・石油製品タンカー運賃先物連動)
    "global_shipping": "BDRY,BWET,ZIM",     # ドライバルク・タンカー・コンテナ複合
    "jp_liners": "9101.T,9104.T,9107.T",    # 邦船大手3社（日本郵船・商船三井・川崎汽船 / ONE 親会社）
}

# FRED 経由で月次取得できる公的運賃 PPI・Cass 物流指数のプリセット
FREIGHT_INDEX_SERIES: dict[str, str] = {
    "deep_sea_freight_ppi": "PCU483111483111",  # 米労働統計局 (BLS) 外航貨物（深海海運）輸送運賃 PPI
    "air_freight_ppi": "PCU481112481112",       # BLS 定期航空貨物輸送運賃 PPI
    "trucking_freight_ppi": "PCU484121484121",  # BLS 長距離トラック貨物輸送運賃 PPI
    "cass_shipments": "FRGSHPUSM649NCIS",       # Cass 貨物輸送指数（出荷量）
    "cass_expenditures": "FRGEXPUSM649NCIS",    # Cass 貨物輸送指数（物流支払額）
    "tsi_freight": "TSIFRGHT",                  # 米国運輸省 (BTS) 貨物輸送サービス指数
}


def fetch_freight_data(
    tickers: str = "BDRY",
    start_date: str | None = None,
    end_date: str | None = None,
    output_file: str | None = None,
) -> pl.DataFrame:
    """
    海運・物流コストの先行指標（ETFや関連株）を取得するわ。
    BDRY (Breakwave Dry Bulk Shipping ETF) はバルチック海運指数に近い動きをするの。
    tickers はカンマ区切り・スペース区切り、または FREIGHT_ETF_PRESETS のキー（dry_bulk, tanker, jp_liners 等）を指定できる。
    """
    resolved_tickers = FREIGHT_ETF_PRESETS.get(tickers.strip().lower(), tickers)
    print(f"Fetching Freight proxy data ({resolved_tickers})...")

    data = fetch_yahoo_finance(resolved_tickers, start_date=start_date, end_date=end_date, interval="1d")

    # 従来の出力スキーマ（Date 文字列 / Ticker / Close / High / Low / Open / Volume）に合わせる
    df = data.rename({"date": "Date", "value": "Close"}).with_columns(
        pl.col("Date").dt.strftime("%Y-%m-%d")
    )
    df = df.filter(pl.col("Close").is_not_null())
    lead = [c for c in ("Date", "Ticker", "Close") if c in df.columns]
    df = df.select(lead + [c for c in df.columns if c not in lead])

    save_output(df, output_file)
    return df


def fetch_freight_index(
    series: str = "deep_sea_freight_ppi",
    start_date: str | None = None,
    end_date: str | None = None,
    output_file: str | None = None,
) -> pl.DataFrame:
    """
    FRED 経由で公的な海運・航空・トラック運賃指数（BLS PPI）および Cass 物流指数を取得する。
    - 'deep_sea_freight_ppi': 外航貨物（深海海運）輸送運賃 PPI (PCU483111483111)
    - 'air_freight_ppi': 定期航空貨物輸送運賃 PPI (PCU481112481112)
    - 'trucking_freight_ppi': 長距離トラック貨物輸送運賃 PPI (PCU484121484121)
    - 'cass_shipments': Cass 貨物輸送指数・出荷量 (FRGSHPUSM649NCIS)
    - 'cass_expenditures': Cass 貨物輸送指数・物流支払額 (FRGEXPUSM649NCIS)
    - 'tsi_freight': 米国運輸省 貨物輸送サービス指数 (TSIFRGHT)
    """
    return fetch_fred_alias(FREIGHT_INDEX_SERIES, series, start_date, end_date, output_file)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Freight & Logistics cost proxy and official index data.")
    parser.add_argument(
        "--tickers",
        default="BDRY",
        help=f"Comma/space-separated tickers or preset {list(FREIGHT_ETF_PRESETS.keys())}. Default: BDRY",
    )
    parser.add_argument(
        "--index",
        help=f"Fetch official FRED freight index instead of Yahoo ETF. Aliases: {list(FREIGHT_INDEX_SERIES.keys())}",
    )
    parser.add_argument("--start", help="Start date (YYYY-MM-DD).")
    parser.add_argument("--end", help="End date (YYYY-MM-DD).")
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    if args.index:
        fetch_freight_index(args.index, args.start, args.end, args.out)
    else:
        fetch_freight_data(args.tickers, args.start, args.end, args.out)


if __name__ == "__main__":
    cli_entry(main)
