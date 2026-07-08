import argparse
from datetime import UTC, datetime, timedelta

import polars as pl
import requests
from dotenv import load_dotenv

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
    try:
        from api_utils import require_api_key
    except ImportError:
        from .api_utils import require_api_key

    api_key = require_api_key(
        "ENTSOE_API_KEY", "ENTSO-E",
        "https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html"
    )

    area = AREA_EIC.get(country.upper(), country)
    if data_type not in DOC_TYPES:
        raise ValueError(f"Unknown data_type: {data_type}. Available: {list(DOC_TYPES.keys())}")
    doc_type, process_type = DOC_TYPES[data_type]

    if not start_date:
        start_date = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%d")
    if not end_date:
        end_date = datetime.now(UTC).strftime("%Y-%m-%d")

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
        response = requests.get(BASE_URL, params=params, timeout=60)
        response.raise_for_status()

        # ENTSO-E は XML を返す
        import xml.etree.ElementTree as ET
        root = ET.fromstring(response.text)
        ns = {"ns": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}

        records = []
        for ts in root.findall(".//ns:TimeSeries", ns) if ns else root.findall(".//TimeSeries"):
            period = ts.find("ns:Period", ns) if ns else ts.find("Period")
            if period is None:
                continue
            start_elem = period.find("ns:timeInterval/ns:start", ns) if ns else period.find("timeInterval/start")
            resolution = period.find("ns:resolution", ns) if ns else period.find("resolution")
            base_start = start_elem.text if start_elem is not None else None
            res_text = resolution.text if resolution is not None else "PT60M"

            for pt in period.findall("ns:Point", ns) if ns else period.findall("Point"):
                pos = pt.find("ns:position", ns) if ns else pt.find("position")
                qty = pt.find("ns:quantity", ns) if ns else pt.find("quantity")
                price = pt.find("ns:price.amount", ns) if ns else pt.find("price.amount")
                value = qty.text if qty is not None else (price.text if price is not None else None)
                records.append({
                    "period_start": base_start,
                    "position": int(pos.text) if pos is not None else None,
                    "resolution": res_text,
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

        if output_file:
            print(f"Saving to {output_file}...")
            df.write_csv(output_file)
        return df
    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error: {e.response.text[:300] if e.response else str(e)}")
        return pl.DataFrame()
    except Exception as e:  # noqa: BLE001
        print(f"Error fetching ENTSO-E data: {e}")
        return pl.DataFrame()


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
    main()
