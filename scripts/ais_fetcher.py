import argparse
import os

import polars as pl
import requests
from dotenv import load_dotenv

load_dotenv()

# 主要港湾座標 (WGS84) - 港湾混雑の代理計測用
MAJOR_PORTS = {
    "shanghai":    {"lat": 31.2304, "lon": 121.4737, "radius_km": 30},
    "singapore":   {"lat": 1.2649,  "lon": 103.8245, "radius_km": 25},
    "rotterdam":   {"lat": 51.9500, "lon": 4.1333,   "radius_km": 20},
    "los_angeles": {"lat": 33.7360, "lon": -118.2640, "radius_km": 25},
    "long_beach":  {"lat": 33.7500, "lon": -118.2000, "radius_km": 20},
    "ningbo":      {"lat": 29.8683, "lon": 121.5440, "radius_km": 25},
    "busan":       {"lat": 35.1028, "lon": 129.0403, "radius_km": 20},
    "hong_kong":   {"lat": 22.3193, "lon": 114.1694, "radius_km": 20},
    "hamburg":     {"lat": 53.5411, "lon": 9.9842,   "radius_km": 15},
    "antwerp":     {"lat": 51.2993, "lon": 4.4014,   "radius_km": 20},
    "tokyo":       {"lat": 35.6195, "lon": 139.7700, "radius_km": 15},
    "yokohama":    {"lat": 35.4437, "lon": 139.6380, "radius_km": 15},
    "nagoya":      {"lat": 35.0833, "lon": 136.8833, "radius_km": 15},
    "suez":        {"lat": 30.5852, "lon": 32.2654,  "radius_km": 30},
    "panama":      {"lat": 9.0820,  "lon": -79.6803, "radius_km": 30},
}


def fetch_ais_datalastic(
    port: str,
    api_key: str,
    vessel_type: str | None = None,
) -> pl.DataFrame:
    """Datalastic API経由で港湾近傍の船舶データを取得"""
    if port not in MAJOR_PORTS:
        raise ValueError(f"Unknown port: {port}. Available: {list(MAJOR_PORTS.keys())}")

    p = MAJOR_PORTS[port]
    url = "https://api.datalastic.com/api/v0/vessel_inradius"
    params = {
        "api-key": api_key,
        "lat": p["lat"],
        "lon": p["lon"],
        "radius": p["radius_km"],
    }
    if vessel_type:
        params["type"] = vessel_type

    response = requests.get(url, params=params, timeout=60)
    response.raise_for_status()
    data = response.json()

    vessels = data.get("data", {}).get("vessels", [])
    if not vessels:
        return pl.DataFrame()

    return pl.DataFrame(vessels)


def fetch_ais_aishub(
    username: str,
    bbox: tuple[float, float, float, float] | None = None,
) -> pl.DataFrame:
    """
    AISHub (無料登録制) からAISデータを取得。
    bbox: (lat_min, lon_min, lat_max, lon_max)
    """
    url = "https://data.aishub.net/ws.php"
    params = {
        "username": username,
        "format": 1,
        "output": "json",
        "compress": 0,
    }
    if bbox:
        params["latmin"], params["lonmin"], params["latmax"], params["lonmax"] = bbox

    response = requests.get(url, params=params, timeout=60)
    response.raise_for_status()

    try:
        data = response.json()
    except Exception:  # noqa: BLE001
        print(f"AISHub response parse error: {response.text[:200]}")
        return pl.DataFrame()

    if isinstance(data, list) and len(data) >= 2:
        vessels = data[1] if isinstance(data[1], list) else []
        if vessels:
            return pl.DataFrame(vessels)

    return pl.DataFrame()


def fetch_ais_data(
    port: str = "shanghai",
    provider: str = "auto",
    vessel_type: str | None = None,
    output_file: str | None = None,
) -> pl.DataFrame:
    """
    AIS / 港湾混雑データを取得するわ。
    - provider: 'datalastic' (要 DATALASTIC_API_KEY) / 'aishub' (要 AISHUB_USERNAME) / 'auto'
    - port: 主要港湾のエイリアス (shanghai/singapore/la/...)
    - vessel_type: 'cargo', 'tanker', 'container' など (Datalastic)
    """
    datalastic_key = os.getenv("DATALASTIC_API_KEY")
    aishub_user = os.getenv("AISHUB_USERNAME")

    df = pl.DataFrame()

    if provider in ("datalastic", "auto") and datalastic_key:
        print(f"Fetching AIS via Datalastic for port={port}...")
        try:
            df = fetch_ais_datalastic(port, datalastic_key, vessel_type)
        except Exception as e:  # noqa: BLE001
            print(f"Datalastic failed: {e}")
            df = pl.DataFrame()

    if df.is_empty() and provider in ("aishub", "auto") and aishub_user:
        print("Fetching AIS via AISHub fallback...")
        if port in MAJOR_PORTS:
            p = MAJOR_PORTS[port]
            deg = p["radius_km"] / 111.0  # km → degree approx
            bbox = (p["lat"] - deg, p["lon"] - deg, p["lat"] + deg, p["lon"] + deg)
        else:
            bbox = None
        try:
            df = fetch_ais_aishub(aishub_user, bbox)
        except Exception as e:  # noqa: BLE001
            print(f"AISHub failed: {e}")

    if df.is_empty():
        print(
            "❌ AIS data not available. Set DATALASTIC_API_KEY (https://datalastic.com) "
            "or AISHUB_USERNAME (https://www.aishub.net/) in .env"
        )
        return df

    # サマリ: 船舶数カウント（混雑度指標）
    n_vessels = df.height
    print(f"[AIS] {port}: {n_vessels} vessels detected (congestion proxy).")

    if output_file:
        print(f"Saving to {output_file}...")
        df.write_csv(output_file)

    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch AIS / port congestion data.")
    parser.add_argument("--port", default="shanghai", help=f"Port alias: {list(MAJOR_PORTS.keys())}")
    parser.add_argument("--provider", default="auto", choices=["auto", "datalastic", "aishub"])
    parser.add_argument("--vessel-type", help="cargo / tanker / container ...")
    parser.add_argument("--out", help="Output CSV filename.")
    args = parser.parse_args()
    fetch_ais_data(
        port=args.port,
        provider=args.provider,
        vessel_type=args.vessel_type,
        output_file=args.out,
    )


if __name__ == "__main__":
    main()
