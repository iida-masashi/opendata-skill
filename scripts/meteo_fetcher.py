import argparse
import math
from collections.abc import Sequence
from typing import Any

import polars as pl
import requests
from api_utils import cli_entry, format_http_error, save_output
from api_utils import get_with_retry as _get_with_retry


def apply_date_range(params: dict[str, Any], start_date: str | None, end_date: str | None) -> None:
    """Open-Meteo 系 API の start_date/end_date を params に入れる（両方指定か両方省略のみ可）。

    片方だけ渡すと Open-Meteo は 400 を返す。黙って捨てると既定期間のデータが
    指定期間のものとして返ってしまうので、ValueError にする。
    """
    if bool(start_date) != bool(end_date):
        raise ValueError(
            "start_date と end_date は両方指定するか、両方省略してください "
            f"(start_date={start_date!r}, end_date={end_date!r})"
        )
    if start_date and end_date:
        params["start_date"] = start_date
        params["end_date"] = end_date


def request_open_meteo(url: str, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Open-Meteo 系 API を呼んで JSON を返す。エラーは理由 (reason) 付きで送出する。"""
    try:
        response = _get_with_retry(url, params=params, **kwargs)
    except requests.exceptions.HTTPError as e:
        # 400 の本文 {"error": true, "reason": "..."} に原因が入る
        raise RuntimeError(f"Open-Meteo {format_http_error(e)}") from e
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected Open-Meteo response: {str(data)[:300]}")
    if data.get("error"):
        raise RuntimeError(f"Open-Meteo API error: {data.get('reason')}")
    return data


def _percentile(sorted_vals: list[float], q: float) -> float:
    """ソート済みリストから線形補間で分位点 q (0.0〜1.0) を計算する。"""
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_vals[lo]
    weight = pos - lo
    return sorted_vals[lo] * (1.0 - weight) + sorted_vals[hi] * weight


def fetch_open_meteo(
    latitude: float,
    longitude: float,
    output_file: str | None = None,
    historical: bool = False,
    hourly: bool | None = None,
    daily: bool = False,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """
    Fetches weather data from Open-Meteo API.
    - daily=True なら日次データ、それ以外は時間別データを返す（hourly 省略時は daily の逆）。
      時間別と日次は行の粒度が違い1つの DataFrame に混ぜられないため、両方 True は ValueError。
    - start_date / end_date は両方指定するか両方省略する。
    """
    if hourly is None:
        hourly = not daily
    if hourly and daily:
        raise ValueError("hourly と daily は同時に指定できません（どちらか一方を True にしてください）")
    if not hourly and not daily:
        raise ValueError("hourly か daily のどちらかを True にしてください")

    base_url = "https://api.open-meteo.com/v1/forecast"
    if historical:
        base_url = "https://archive-api.open-meteo.com/v1/archive"

    # Default params
    params: dict[str, Any] = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": "auto",
        "current_weather": True,
    }

    apply_date_range(params, start_date, end_date)

    # Variables
    hourly_vars = [
        "temperature_2m", "relative_humidity_2m", "precipitation", "rain",
        "showers", "snowfall", "weathercode", "cloudcover", "windspeed_10m",
    ]
    daily_vars = [
        "temperature_2m_max", "temperature_2m_min", "precipitation_sum",
        "rain_sum", "showers_sum", "snowfall_sum", "weathercode", "windspeed_10m_max",
    ]

    section = "daily" if daily else "hourly"
    params[section] = ",".join(daily_vars if daily else hourly_vars)

    print(f"Fetching weather data (Lat: {latitude}, Lon: {longitude}, {section})...")
    data = request_open_meteo(base_url, params)

    # Open-Meteo returns 'hourly': {'time': [...], 'temp': [...], ...}
    if section not in data:
        raise RuntimeError(f"Open-Meteo response has no '{section}' data (keys: {sorted(data)})")

    df = pl.DataFrame(data[section]).with_columns(pl.lit(section).alias("type"))

    save_output(df, output_file)
    return df


def fetch_open_meteo_ensemble(
    latitude: float,
    longitude: float,
    variables: str | Sequence[str] | None = None,
    model: str = "icon_seamless",
    daily: bool = True,
    start_date: str | None = None,
    end_date: str | None = None,
    output_file: str | None = None,
) -> pl.DataFrame:
    """
    Open-Meteo Ensemble API からアンサンブル気象予報を取得し、
    各変数のメンバー間統計量（mean, std, p10, p50, p90, min, max）を集計して返す。
    安全在庫計算や需要の上振れ・下振れシナリオ評価に最適。APIキー不要。
    """
    base_url = "https://ensemble-api.open-meteo.com/v1/ensemble"
    section = "daily" if daily else "hourly"

    if variables is None:
        var_list = (
            ["temperature_2m_max", "temperature_2m_min", "precipitation_sum"]
            if daily
            else ["temperature_2m", "precipitation"]
        )
    elif isinstance(variables, str):
        var_list = [v.strip() for v in variables.split(",") if v.strip()]
    else:
        var_list = [str(v).strip() for v in variables if str(v).strip()]

    if not var_list:
        raise ValueError("variables must not be empty")

    params: dict[str, Any] = {
        "latitude": latitude,
        "longitude": longitude,
        "models": model,
        "timezone": "auto",
        section: ",".join(var_list),
    }
    apply_date_range(params, start_date, end_date)

    print(f"Fetching Open-Meteo Ensemble ({model}, Lat: {latitude}, Lon: {longitude}, {section})...")
    data = request_open_meteo(base_url, params)

    if section not in data:
        raise RuntimeError(f"Open-Meteo Ensemble response has no '{section}' data (keys: {sorted(data)})")

    sec_data = data[section]
    times = sec_data.get("time", [])
    n_rows = len(times)
    if n_rows == 0:
        return pl.DataFrame()

    rows: list[dict[str, Any]] = []
    for idx in range(n_rows):
        row: dict[str, Any] = {
            "date": str(times[idx]),
            "time": str(times[idx]),
            "model": model,
            "type": section,
        }
        for v_idx, var in enumerate(var_list):
            member_cols = [
                k for k in sec_data
                if k == var or k.startswith(f"{var}_member")
            ]
            vals: list[float] = []
            for mc in member_cols:
                col_vals = sec_data.get(mc, [])
                if idx < len(col_vals) and col_vals[idx] is not None:
                    vals.append(float(col_vals[idx]))
            if vals:
                vals.sort()
                mean_val = sum(vals) / len(vals)
                variance = sum((x - mean_val) ** 2 for x in vals) / len(vals)
                std_val = math.sqrt(variance)
                row[f"{var}_mean"] = mean_val
                row[f"{var}_std"] = std_val
                row[f"{var}_p10"] = _percentile(vals, 0.10)
                row[f"{var}_p50"] = _percentile(vals, 0.50)
                row[f"{var}_p90"] = _percentile(vals, 0.90)
                row[f"{var}_min"] = vals[0]
                row[f"{var}_max"] = vals[-1]
                if v_idx == 0:
                    row["value"] = mean_val
            else:
                row[f"{var}_mean"] = None
                row[f"{var}_std"] = None
                row[f"{var}_p10"] = None
                row[f"{var}_p50"] = None
                row[f"{var}_p90"] = None
                row[f"{var}_min"] = None
                row[f"{var}_max"] = None
                if v_idx == 0:
                    row["value"] = None
        rows.append(row)

    df = pl.DataFrame(rows)
    save_output(df, output_file)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch weather or ensemble forecast data from Open-Meteo.")
    parser.add_argument("--lat", required=True, type=float, help="Latitude")
    parser.add_argument("--lon", required=True, type=float, help="Longitude")
    parser.add_argument("--out", help="Output CSV filename")
    parser.add_argument("--historical", action="store_true", help="Fetch historical data (archive API)")
    parser.add_argument("--daily", action="store_true", help="Fetch daily data instead of hourly")
    parser.add_argument("--ensemble", action="store_true", help="Fetch ensemble probabilistic forecast")
    parser.add_argument("--model", default="icon_seamless", help="Ensemble weather model (default: icon_seamless)")
    parser.add_argument("--start", help="Start date (YYYY-MM-DD). Use together with --end")
    parser.add_argument("--end", help="End date (YYYY-MM-DD). Use together with --start")

    args = parser.parse_args()
    output_file = args.out
    if args.ensemble:
        if not output_file:
            output_file = f"meteo_ensemble_{args.lat}_{args.lon}.csv"
        fetch_open_meteo_ensemble(
            args.lat,
            args.lon,
            model=args.model,
            daily=True if not args.historical else args.daily,
            start_date=args.start,
            end_date=args.end,
            output_file=output_file,
        )
    else:
        if not output_file:
            mode = "historical" if args.historical else "forecast"
            output_file = f"meteo_{mode}_{args.lat}_{args.lon}.csv"
        fetch_open_meteo(
            args.lat, args.lon, output_file, args.historical, not args.daily, args.daily, args.start, args.end
        )


if __name__ == "__main__":
    cli_entry(main)
