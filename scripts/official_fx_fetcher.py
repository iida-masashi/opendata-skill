import argparse
from io import StringIO

import polars as pl
import requests  # noqa: F401 - テストが official_fx_fetcher.requests.get を patch する
from api_utils import cli_entry, default_date_range, save_output
from api_utils import get_with_retry as _get_with_retry

# ECB Statistical Data Warehouse (SDMX 2.1) - APIキー不要
ECB_BASE = "https://data-api.ecb.europa.eu/service/data/EXR"
# BOJ 時系列統計データ検索サイト (BIS) - 日銀公表レート
BOJ_BASE = "https://www.stat-search.boj.or.jp/ssi/cgi-bin/famecgi2"


def fetch_ecb_fx(
    currency: str = "JPY",
    start_date: str | None = None,
    end_date: str | None = None,
    frequency: str = "D",  # D=daily, M=monthly, A=annual
) -> pl.DataFrame:
    """
    ECB 公式為替レート (対ユーロ) を取得。
    EUR/USD, EUR/JPY, EUR/GBP など会計・決算用の公的レート。
    """
    # ECB SDMX key format: {freq}.{currency}.EUR.SP00.A
    key = f"{frequency}.{currency.upper()}.EUR.SP00.A"
    url = f"{ECB_BASE}/{key}"

    start_date, end_date = default_date_range(start_date, end_date, days=365 * 2)

    params = {
        "startPeriod": start_date,
        "endPeriod": end_date,
        "format": "csvdata",
    }
    headers = {"Accept": "text/csv"}

    print(f"Fetching ECB official FX: EUR/{currency} ({start_date}→{end_date})...")
    response = _get_with_retry(url, params=params, headers=headers)

    if not response.text.strip():
        # 正常応答で本文が空 = 該当期間のデータ0件
        return pl.DataFrame()
    df = pl.read_csv(StringIO(response.text))

    if df.is_empty():
        return df

    # 標準化
    if "TIME_PERIOD" in df.columns:
        df = df.with_columns(pl.col("TIME_PERIOD").alias("date"))
    if "OBS_VALUE" in df.columns:
        df = df.with_columns(pl.col("OBS_VALUE").cast(pl.Float64, strict=False).alias("value"))

    df = df.with_columns(
        pl.lit(f"EUR/{currency.upper()}").alias("pair"),
        pl.lit("ECB").alias("source"),
    )
    return df


_JPY_SUPPORTED = {"USD", "EUR", "GBP", "CNY", "AUD", "CAD", "CHF", "HKD", "SGD", "KRW"}


def fetch_jpy_fx(
    currency: str = "USD",
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """
    円建て為替レートを Frankfurter API (ECBデータソース) 経由で取得。

    ⚠️ 注意: これは BOJ の公式基準レートではありません。
    Frankfurter は ECB の日次参照レートを配信しているため、実体は
    「ECBレートから算出した円建てクロスレート」です。
    BOJ公表の基準外国為替相場が必要な場合は日銀時系列統計サイトから
    CSV をダウンロードしてください (https://www.stat-search.boj.or.jp/)。
    """
    curr = currency.upper()
    if curr not in _JPY_SUPPORTED:
        raise ValueError(
            f"JPY FX not supported for {curr}. Supported: {sorted(_JPY_SUPPORTED)}"
        )

    start_date, end_date = default_date_range(start_date, end_date, days=365 * 2)
    start_date = start_date.replace("-", "")
    end_date = end_date.replace("-", "")

    print(f"Fetching JPY FX via Frankfurter (ECB-derived): {curr}/JPY ({start_date}→{end_date})...")

    url = (
        f"https://api.frankfurter.app/"
        f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}.."
        f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}"
    )
    params = {"from": curr, "to": "JPY"}

    response = _get_with_retry(url, params=params)
    data = response.json()
    if not isinstance(data, dict) or "rates" not in data:
        msg = data.get("message") if isinstance(data, dict) else None
        raise RuntimeError(f"Frankfurter API error: {msg or str(data)[:300]}")
    rates = data["rates"]
    records = [{"date": d, "value": r.get("JPY")} for d, r in rates.items()]
    if not records:
        return pl.DataFrame()
    df = pl.DataFrame(records).sort("date")
    df = df.with_columns(
        pl.lit(f"{curr}/JPY").alias("pair"),
        pl.lit("Frankfurter (ECB-derived)").alias("source"),
    )
    return df


# 後方互換のエイリアス (deprecated)
fetch_boj_fx = fetch_jpy_fx


def fetch_official_fx(
    source: str = "ecb",
    currency: str = "JPY",
    start_date: str | None = None,
    end_date: str | None = None,
    output_file: str | None = None,
) -> pl.DataFrame:
    """
    公的機関の公表為替レートを取得するわ。
    - source: 'ecb' (ECB/Eurosystem) / 'boj' (円建て: Frankfurter 経由の ECB 由来クロスレート)
    - currency: ecb は対ユーロの相手通貨、boj は対円の基準通貨（USD/EUR/...）。
      boj で 'JPY'（既定値。Hub も既定で渡す）が来た場合は JPY/JPY は無意味なので USD/JPY を返す。
    - 用途: 会計・決算・税務・契約用の公式レート（Yahooの市場値とは区別）
    """
    if source.lower() == "ecb":
        df = fetch_ecb_fx(currency=currency, start_date=start_date, end_date=end_date)
    elif source.lower() == "boj":
        if currency.upper() == "JPY":
            print("source='boj' は円建てレートのため currency='JPY' を USD (USD/JPY) として扱います。")
            currency = "USD"
        df = fetch_boj_fx(currency=currency, start_date=start_date, end_date=end_date)
    else:
        raise ValueError(f"Unknown source: {source}")

    if df.is_empty():
        print("No official FX data found.")
        return df

    save_output(df, output_file)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch official FX rates (ECB / BOJ).")
    parser.add_argument("--source", default="ecb", choices=["ecb", "boj"])
    parser.add_argument("--currency", default="JPY", help="Currency code (JPY, USD, GBP, ...)")
    parser.add_argument("--start", help="Start date (YYYY-MM-DD).")
    parser.add_argument("--end", help="End date (YYYY-MM-DD).")
    parser.add_argument("--out", help="Output CSV filename.")
    args = parser.parse_args()
    fetch_official_fx(
        source=args.source,
        currency=args.currency,
        start_date=args.start,
        end_date=args.end,
        output_file=args.out,
    )


if __name__ == "__main__":
    cli_entry(main)
