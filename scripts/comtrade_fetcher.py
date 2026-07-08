import argparse
import os
from datetime import UTC, datetime

import polars as pl
import requests
from dotenv import load_dotenv

load_dotenv()

# UN Comtrade Public API v1 (Free tier: 500 records/query, 100 queries/hour without key)
# Premium API (with subscription key) allows higher limits.
BASE_URL_PUBLIC = "https://comtradeapi.un.org/public/v1/preview"
BASE_URL_PREMIUM = "https://comtradeapi.un.org/data/v1/get"

# 主要国ISO3コード → M49コード（Comtrade標準）
COUNTRY_M49 = {
    "JP": "392",   # Japan
    "US": "842",   # USA
    "CN": "156",   # China
    "DE": "276",   # Germany
    "KR": "410",   # Korea Rep.
    "TW": "158",   # Taiwan
    "VN": "704",   # Vietnam
    "TH": "764",   # Thailand
    "IN": "699",   # India
    "ALL": "0",    # World aggregate (M49 code for "World" is 0)
}


def fetch_comtrade_data(
    reporter: str = "JP",
    partner: str = "ALL",
    period: str | None = None,
    hs_code: str = "TOTAL",
    flow: str = "M",  # M=Import, X=Export
    frequency: str = "A",  # A=Annual, M=Monthly
    output_file: str | None = None,
) -> pl.DataFrame:
    """
    UN Comtrade からグローバル貿易フローを取得するわ。
    - reporter: 報告国 (ISO2: JP/US/CN...)
    - partner: 相手国 (ALL=全世界集計)
    - hs_code: HSコード (例: '8703'=乗用車, '8542'=集積回路, 'TOTAL'=総額)
    - flow: M (輸入) / X (輸出)
    - frequency: A (年次) / M (月次)
    - period: 年または年月 (例: '2023', '202312', '2022,2023')
    """
    reporter_code = COUNTRY_M49.get(reporter.upper(), reporter)
    partner_code = COUNTRY_M49.get(partner.upper(), partner)

    if not period:
        period = str(datetime.now(UTC).year - 1)

    subscription_key = os.getenv("COMTRADE_API_KEY")

    if subscription_key:
        url = f"{BASE_URL_PREMIUM}/C/{frequency}/HS"
        headers = {"Ocp-Apim-Subscription-Key": subscription_key}
    else:
        url = f"{BASE_URL_PUBLIC}/C/{frequency}/HS"
        headers = {}

    params = {
        "reporterCode": reporter_code,
        "partnerCode": partner_code,
        "period": period,
        "cmdCode": hs_code,
        "flowCode": flow,
        "format": "JSON",
    }

    print(f"Fetching UN Comtrade: reporter={reporter}, partner={partner}, hs={hs_code}, flow={flow}, period={period}...")
    try:
        response = requests.get(url, params=params, headers=headers, timeout=60)
        response.raise_for_status()
        data = response.json()

        records = data.get("data", []) if isinstance(data, dict) else []
        if not records:
            print("No trade data found.")
            return pl.DataFrame()

        df = pl.DataFrame(records)
        # 主要カラムを抽出 (Comtradeの標準スキーマ)
        keep_cols = [
            c for c in [
                "period", "reporterISO", "reporterDesc",
                "partnerISO", "partnerDesc", "cmdCode", "cmdDesc",
                "flowCode", "flowDesc", "primaryValue", "netWgt", "qty",
            ] if c in df.columns
        ]
        if keep_cols:
            df = df.select(keep_cols)

        # 日付カラム標準化 (period -> date)
        if "period" in df.columns:
            df = df.with_columns(pl.col("period").cast(pl.Utf8).alias("date"))
        if "primaryValue" in df.columns:
            df = df.with_columns(pl.col("primaryValue").alias("value"))

        if output_file:
            print(f"Saving to {output_file}...")
            df.write_csv(output_file)

        return df
    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error: {e.response.text if e.response else str(e)}")
        return pl.DataFrame()
    except Exception as e:  # noqa: BLE001
        print(f"Error fetching Comtrade: {e}")
        return pl.DataFrame()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch global trade flow from UN Comtrade.")
    parser.add_argument("--reporter", default="JP", help="Reporter country (ISO2 or M49).")
    parser.add_argument("--partner", default="ALL", help="Partner country.")
    parser.add_argument("--period", help="Period (YYYY or YYYYMM).")
    parser.add_argument("--hs", default="TOTAL", help="HS commodity code.")
    parser.add_argument("--flow", default="M", choices=["M", "X"], help="M=Import, X=Export.")
    parser.add_argument("--freq", default="A", choices=["A", "M"], help="A=Annual, M=Monthly.")
    parser.add_argument("--out", help="Output CSV filename.")
    args = parser.parse_args()
    fetch_comtrade_data(
        reporter=args.reporter,
        partner=args.partner,
        period=args.period,
        hs_code=args.hs,
        flow=args.flow,
        frequency=args.freq,
        output_file=args.out,
    )


if __name__ == "__main__":
    main()
