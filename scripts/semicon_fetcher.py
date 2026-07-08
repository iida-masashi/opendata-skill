import argparse

import polars as pl
from dotenv import load_dotenv

try:
    from fred_fetcher import fetch_fred_data
except ImportError:
    from .fred_fetcher import fetch_fred_data

load_dotenv()

# 半導体業界指標 (FRED経由で取得可能な公開データ)
# WSTS/SEMI Book-to-Bill本体は会員制のため、FREDの公開代替系列を活用
SEMI_SERIES = {
    # --- 米国 製造業・半導体関連 ---
    "us_semi_shipments":    "A34SNO",            # 半導体・その他電子部品 新規受注
    "us_semi_inventories":  "A34STI",            # 半導体・その他電子部品 在庫
    "us_semi_ship_val":     "A34SVS",            # 半導体・その他電子部品 出荷額
    "us_ict_prod":          "IPG3341S",          # コンピュータ・電子製品 生産指数
    # --- 日本 鉱工業統計（e-Stat経由の代替） ---
    "jp_ic_prod":           "JPNPRINTO01IXOBSAM",  # 日本産業生産 (OECD経由)
    # --- 韓国 ---
    "kr_export_semi":       "XTEXVA01KRM664S",   # 韓国 輸出額（半導体主要輸出国）
    # --- 台湾 ---
    "tw_export":            "XTEXVA01TWM664S",   # 台湾 輸出額
}


def fetch_semicon_data(
    series: str = "us_semi_shipments",
    start_date: str | None = None,
    end_date: str | None = None,
    output_file: str | None = None,
) -> pl.DataFrame:
    """
    半導体業界の出荷・在庫・受注データを FRED 経由で取得するわ。
    WSTS/SEMI Book-to-Bill本体は会員限定なので、FREDで公開されている代替系列（実質的に同等シグナル）を提供。
    - 'us_semi_shipments': 米製造業統計 半導体新規受注
    - 'us_semi_inventories': 半導体在庫
    - 'us_semi_ship_val': 半導体出荷額
    - Book-to-Bill比は compute_book_to_bill() で計算可能
    """
    series_id = SEMI_SERIES.get(series.lower(), series)

    df = fetch_fred_data(
        series_id=series_id,
        start_date=start_date,
        end_date=end_date,
        output_file=None,
    )
    if df.is_empty():
        return df

    df = df.with_columns(pl.lit(series).alias("series"))

    if output_file:
        print(f"Saving to {output_file}...")
        df.write_csv(output_file)
    return df


def compute_book_to_bill(
    start_date: str | None = None,
    end_date: str | None = None,
    output_file: str | None = None,
) -> pl.DataFrame:
    """
    米半導体業界の Book-to-Bill 比を自動計算。
    値 > 1.0 は需要>供給（業界拡張期）、< 1.0 は収縮期を示す。
    """
    orders = fetch_semicon_data("us_semi_shipments", start_date, end_date)
    ships = fetch_semicon_data("us_semi_ship_val", start_date, end_date)

    if orders.is_empty() or ships.is_empty():
        return pl.DataFrame()

    orders = orders.select(["date", "value"]).rename({"value": "new_orders"})
    ships = ships.select(["date", "value"]).rename({"value": "shipments"})
    df = orders.join(ships, on="date", how="inner")
    df = df.with_columns(
        # shipments が 0/null の月は inf を出さず null にする（B2B比は未定義）
        pl.when((pl.col("shipments").is_null()) | (pl.col("shipments") == 0))
        .then(None)
        .otherwise(pl.col("new_orders") / pl.col("shipments"))
        .alias("book_to_bill"),
    )
    df = df.with_columns(pl.lit("us_semi").alias("series"))

    if output_file:
        print(f"Saving B2B ratio to {output_file}...")
        df.write_csv(output_file)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch semiconductor industry indicators.")
    parser.add_argument("--series", default="us_semi_shipments", help=f"Series: {list(SEMI_SERIES.keys())} or 'book_to_bill'")
    parser.add_argument("--start", help="Start date (YYYY-MM-DD).")
    parser.add_argument("--end", help="End date (YYYY-MM-DD).")
    parser.add_argument("--out", help="Output CSV filename.")
    args = parser.parse_args()

    if args.series == "book_to_bill":
        compute_book_to_bill(args.start, args.end, args.out)
    else:
        fetch_semicon_data(args.series, args.start, args.end, args.out)


if __name__ == "__main__":
    main()
