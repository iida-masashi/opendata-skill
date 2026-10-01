import argparse

import polars as pl
import requests  # noqa: F401 - テストが jshis_fetcher.requests.get を patch する

from api_utils import cli_entry, save_output
from api_utils import get_with_retry as _get_with_retry


def fetch_jshis_risk(lat: float, lon: float, output_file: str | None = None) -> pl.DataFrame:
    """
    Fetches Earthquake Hazard Risk from J-SHIS API (NIED).
    Specifically, probability of seismic intensity >= 6-lower within 30 years.

    API: http://www.j-shis.bosai.go.jp/api/pshm/ymap/v2/meshinfo.geojson
    This returns mesh info for a point.
    Then we need to parse the probability.

    Wait, the V2 API is better.
    Let's use the Mesh Info API to get the mesh code, then get the probability.
    Actually, the "PSHM" (Probabilistic Seismic Hazard Maps) API returns values for a mesh.

    Endpoint: https://www.j-shis.bosai.go.jp/map/api/pshm/Y2020/AVR/TTL_MTTL/meshinfo.geojson?position={lon},{lat}&epsg=4326
    (Note: Year might change. Y2020 is a standard reference.)
    """  # noqa: E501

    # Using 2020 model (latest major release usually)
    # Case: Average case (AVR), Total Probability (TTL_MTTL)
    base_url = "https://www.j-shis.bosai.go.jp/map/api/pshm/Y2020/AVR/TTL_MTTL/meshinfo.geojson"

    params = {
        "position": f"{lon},{lat}",
        "epsg": "4326"
    }

    print(f"Fetching J-SHIS Earthquake Risk for Lat: {lat}, Lon: {lon}...")

    response = _get_with_retry(base_url, params=params)
    data = response.json()

    features = data.get('features', [])
    if not features:
        print("No data found for this location.")
        return pl.DataFrame()

    # Extract properties
    props = features[0].get('properties', {})

    # Key properties (per J-SHIS PSHM mesh-info spec):
    # T30_I45_PS: Prob of Int >= 5-lower (震度5弱) in 30 years
    # T30_I50_PS: Prob of Int >= 5-upper (震度5強)
    # T30_I55_PS: Prob of Int >= 6-lower (震度6弱)
    # T30_I60_PS: Prob of Int >= 6-upper (震度6強)
    # (Note: there is no T30_I65_PS field; mesh key is lowercase 'meshcode'.)

    risk_data = {
        'MeshCode': props.get('meshcode'),
        'Prob_30Y_Int5L': props.get('T30_I45_PS'),
        'Prob_30Y_Int5U': props.get('T30_I50_PS'),
        'Prob_30Y_Int6L': props.get('T30_I55_PS'),
        'Prob_30Y_Int6U': props.get('T30_I60_PS'),
        'Latitude': lat,
        'Longitude': lon
    }

    df = pl.DataFrame([risk_data])
    save_output(df, output_file)
    print("Risk Probabilities (30 Years):")
    print(df)
    return df

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Earthquake Risk (J-SHIS).")
    parser.add_argument("--lat", required=True, type=float, help="Latitude")
    parser.add_argument("--lon", required=True, type=float, help="Longitude")
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    fetch_jshis_risk(args.lat, args.lon, args.out or f"jshis_risk_{args.lat}_{args.lon}.csv")

if __name__ == "__main__":
    cli_entry(main)
