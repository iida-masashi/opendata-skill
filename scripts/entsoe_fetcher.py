import argparse
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta

import polars as pl
import requests
from dotenv import load_dotenv

from api_utils import (
    cli_entry,
    default_date_range,
    redact,
    require_api_key,
    save_output,
)
from api_utils import get_with_retry_redacted as _get_redacted

load_dotenv()

BASE_URL = "https://web-api.tp.entsoe.eu/api"

# 欧州主要国 ENTSO-E Area EIC コード
AREA_EIC = {
    "DE":    "10Y1001A1001A83F",  # Germany
    "FR":    "10YFR-RTE------C",  # France
    "IT":    "10YIT-GRTN-----B",  # Italy
    "ES":    "10YES-REE------0",  # Spain
    "NL":    "10YNL----------L",  # Netherlands
    "BE":    "10YBE----------2",  # Belgium
    "GB":    "10YGB----------A",  # Great Britain
    "PL":    "10YPL-AREA-----S",  # Poland
    "AT":    "10YAT-APG------L",  # Austria
    "CH":    "10YCH-SWISSGRIDZ",  # Switzerland
    "DK":    "10Y1001A1001A65H",  # Denmark
    "NO":    "10YNO-0--------C",  # Norway
    "SE":    "10YSE-1--------K",  # Sweden
    "FI":    "10YFI-1--------U",  # Finland
    "EU":    "10YEU-EURO-----Z",  # EU aggregate
}

# 主要なDocument Type（リクエスト種別）と必須 processType。
# A44 (Day-ahead price) のみ processType 不要。他は ENTSO-E が processType を要求する
# （無いと HTTP 400）。A75=Realised(A16), A71/A69=Day ahead(A01)。
DOC_TYPES = {
    "load_actual":     ("A65", "A16"),   # Actual total load
    "load_forecast":   ("A65", "A01"),   # Day-ahead total load forecast
    "generation":      ("A75", "A16"),   # Actual generation per type (Realised)
    "gen_forecast":    ("A71", "A01"),   # Generation forecast (Day ahead)
    "day_ahead_price": ("A44", None),    # Day-ahead prices (processType不要)
    "wind_solar":      ("A69", "A01"),   # Wind & solar forecast (Day ahead)
}

# 「パラメータは正しいがデータ0件」を示す Acknowledgement の Reason テキスト
NO_DATA_TEXT = "No matching data found"


def _parse_resolution(res: str) -> timedelta:
    """ENTSO-E の resolution (ISO 8601: PT15M / PT60M / P1D 等) を timedelta にする。"""
    m = re.fullmatch(r"PT(\d+)M|PT(\d+)H|P(\d+)D", res)
    if not m:
        raise ValueError(f"Unsupported ENTSO-E resolution: {res}")
    minutes, hours, days = m.groups()
    if minutes:
        return timedelta(minutes=int(minutes))
    if hours:
        return timedelta(hours=int(hours))
    return timedelta(days=int(days))


def fetch_entsoe_data(
    data_type: str = "load_actual",
    country: str = "DE",
    start_date: str | None = None,
    end_date: str | None = None,
    output_file: str | None = None,
) -> pl.DataFrame:
    """
    ENTSO-E Transparency Platform から欧州電力需給データを取得するわ。
    - data_type: 'load_actual', 'load_forecast', 'generation', 'day_ahead_price', 'wind_solar'
    - country: 'DE', 'FR', 'IT', 'ES', ...
    無料だが登録制。APIキー取得: https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html
    """
    api_key = require_api_key(
        "ENTSOE_API_KEY", "ENTSO-E",
        "https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html"
    )

    area = AREA_EIC.get(country.upper(), country)
    if data_type not in DOC_TYPES:
        raise ValueError(f"Unknown data_type: {data_type}. Available: {list(DOC_TYPES.keys())}")
    doc_type, process_type = DOC_TYPES[data_type]

    start_date, end_date = default_date_range(start_date, end_date, 30)

    # ENTSO-E日時形式: YYYYMMDDhhmm
    period_start = start_date.replace("-", "") + "0000"
    period_end = end_date.replace("-", "") + "2300"

    # ENTSO-Eのパラメータ要件はdocumentTypeごとに異なる
    # - Load (A65):       outBiddingZone_Domain のみ
    # - Generation (A75): in_Domain のみ
    # - Wind/Solar (A69): in_Domain のみ
    # - Prices (A44):     in_Domain + out_Domain (同一エリア)
    params: dict[str, str] = {
        "securityToken": api_key,
        "documentType": doc_type,
        "periodStart": period_start,
        "periodEnd": period_end,
    }
    if doc_type == "A44":  # day_ahead_price
        params["in_Domain"] = area
        params["out_Domain"] = area
    elif doc_type == "A65":  # load_actual / load_forecast
        params["outBiddingZone_Domain"] = area
    else:  # A75 / A71 / A69: 発電系
        params["in_Domain"] = area

    if process_type:
        params["processType"] = process_type

    print(f"Fetching ENTSO-E: {data_type} for {country} ({start_date}→{end_date})...")
    try:
        response = _get_redacted(BASE_URL, [api_key], params=params)
    except requests.exceptions.HTTPError as e:
        # ENTSO-E は「パラメータは正しいがデータ0件」を 400 + Acknowledgement で返すことがある
        if e.response is not None and NO_DATA_TEXT in e.response.text:
            print("No ENTSO-E data found (No matching data found).")
            return pl.DataFrame()
        raise

    # ENTSO-E は XML を返す
    root = ET.fromstring(response.text)
    ns = {"ns": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}

    def _find(elem: ET.Element, path: str) -> ET.Element | None:
        return elem.find(path.replace("{ns}", "ns:") if ns else path.replace("{ns}", ""), ns)

    def _findall(elem: ET.Element, path: str) -> list[ET.Element]:
        return elem.findall(path.replace("{ns}", "ns:") if ns else path.replace("{ns}", ""), ns)

    # HTTP 200 で返る Acknowledgement（エラー or 0件通知）
    if root.tag.endswith("Acknowledgement_MarketDocument"):
        reason = " ".join(t.text or "" for t in _findall(root, ".//{ns}Reason/{ns}text"))
        if NO_DATA_TEXT in reason:
            print("No ENTSO-E data found (No matching data found).")
            return pl.DataFrame()
        raise RuntimeError(f"ENTSO-E API error: {redact(reason or response.text[:300], [api_key])}")

    records = []
    for ts in _findall(root, ".//{ns}TimeSeries"):
        psr = _find(ts, "{ns}MktPSRType/{ns}psrType")
        psr_type = psr.text if psr is not None else None
        for period in _findall(ts, "{ns}Period"):
            start_elem = _find(period, "{ns}timeInterval/{ns}start")
            resolution = _find(period, "{ns}resolution")
            base_start = start_elem.text if start_elem is not None else None
            res_text = resolution.text if resolution is not None else "PT60M"
            step = _parse_resolution(res_text)
            start_dt = datetime.strptime(base_start, "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC) if base_start else None

            for pt in _findall(period, "{ns}Point"):
                pos = _find(pt, "{ns}position")
                qty = _find(pt, "{ns}quantity")
                price = _find(pt, "{ns}price.amount")
                value = qty.text if qty is not None else (price.text if price is not None else None)
                position = int(pos.text) if pos is not None else None
                records.append({
                    "date": start_dt + (position - 1) * step if start_dt and position else None,
                    "period_start": base_start,
                    "position": position,
                    "resolution": res_text,
                    "psr_type": psr_type,
                    "value": float(value) if value else None,
                })

    if not records:
        print("No ENTSO-E data found or empty response.")
        return pl.DataFrame()

    df = pl.DataFrame(records).drop_nulls(subset=["value"])
    df = df.with_columns(
        pl.lit(country.upper()).alias("country"),
        pl.lit(data_type).alias("data_type"),
    )

    save_output(df, output_file)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch European power data from ENTSO-E.")
    parser.add_argument("--type", default="load_actual", help=f"Data type: {list(DOC_TYPES.keys())}")
    parser.add_argument("--country", default="DE", help=f"Country: {list(AREA_EIC.keys())}")
    parser.add_argument("--start", help="Start date (YYYY-MM-DD).")
    parser.add_argument("--end", help="End date (YYYY-MM-DD).")
    parser.add_argument("--out", help="Output CSV filename.")
    args = parser.parse_args()
    fetch_entsoe_data(
        data_type=args.type,
        country=args.country,
        start_date=args.start,
        end_date=args.end,
        output_file=args.out,
    )


if __name__ == "__main__":
    cli_entry(main)
