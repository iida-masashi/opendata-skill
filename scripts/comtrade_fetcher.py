import argparse
import os
from datetime import UTC, datetime

import polars as pl
import requests
from api_utils import cli_entry, format_http_error, save_output
from api_utils import get_with_retry as _get_with_retry
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
    "VN": "704",   # Vietnam
    "TH": "764",   # Thailand
    "IN": "699",   # India
    "ALL": "0",    # World aggregate (M49 code for "World" is 0)
}

# Comtrade の参照表 (https://comtradeapi.un.org/files/v1/app/reference/Reporters.json /
# partnerAreas.json) では、台湾は報告国 (reporter) に存在せず、相手国としての 158 は表に
# あっても各国の報告では 490 "Other Asia, nes"（その他アジア・他に分類されないもの）に計上される。
# 158 を送ると黙って0件になるため、別名 TW は受け付けずに理由を示す。
UNSUPPORTED_ALIASES = {
    "TW": (
        "Taiwan is not a UN Comtrade reporter, and partner trade with Taiwan is recorded "
        "under 490 'Other Asia, nes' (code 158 returns no data). "
        "Pass partner='490' explicitly if that aggregate is what you want."
    ),
}


def _resolve_country(code: str) -> str:
    if code.upper() in UNSUPPORTED_ALIASES:
        raise ValueError(UNSUPPORTED_ALIASES[code.upper()])
    return COUNTRY_M49.get(code.upper(), code)


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
    - period: 年または年月 (例: '2023', '202312', '2022,2023')。月次 (frequency='M') は YYYYMM 必須。
      未指定時は前年（月次は前年12月。無料プレビューAPIは1回1期間まで）。
    """
    reporter_code = _resolve_country(reporter)
    partner_code = _resolve_country(partner)

    if not period:
        last_year = datetime.now(UTC).year - 1
        period = f"{last_year}12" if frequency.upper() == "M" else str(last_year)

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
        response = _get_with_retry(url, params=params, headers=headers)
    except requests.exceptions.HTTPError as e:
        # 400 の本文に原因（例: "For monthly frequency, all periods must be in YYYYMM format."）が入る
        raise RuntimeError(f"UN Comtrade {format_http_error(e)}") from e
    data = response.json()

    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected UN Comtrade response: {str(data)[:300]}")  # noqa: TRY004
    # 正常応答でも "error": "" が入るので、空でない場合だけエラー扱い
    if data.get("error"):
        raise RuntimeError(f"UN Comtrade API error: {data['error']}")

    records = data.get("data") or []
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

    save_output(df, output_file)
    return df


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
    cli_entry(main)
