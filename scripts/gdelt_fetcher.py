import argparse
from datetime import UTC, datetime, timedelta
from typing import Any

import polars as pl
import requests

try:
    from api_utils import retry_with_ratelimit
except ImportError:
    from .api_utils import retry_with_ratelimit


@retry_with_ratelimit
def _get_with_retry(url: str, **kwargs: Any) -> requests.Response:
    """module の requests.get を呼びつつ 429/5xx で再試行する（テストは patch 可能なまま）。"""
    kwargs.setdefault("timeout", 60)
    resp = requests.get(url, **kwargs)
    resp.raise_for_status()
    return resp

# GDELT 2.0 DOC API (無料・APIキー不要)
DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
# GDELT Events API (GKG - Global Knowledge Graph)
GKG_API = "https://api.gdeltproject.org/api/v2/gkg/gkg"

# SCM断絶・地政学リスク関連のテーマフィルタ例
SCM_RISK_THEMES = {
    "supply_chain": "SUPPLY_CHAIN",
    "port_congestion": "PORT",
    "strike": "STRIKE",
    "embargo": "ECON_EMBARGO",
    "sanctions": "SANCTIONS",
    "natural_disaster": "NATURAL_DISASTER",
    "conflict": "ARMEDCONFLICT",
    "cyber_attack": "CYBER_ATTACK",
    "chokepoint": "MARITIME_INCIDENT",
}


def fetch_gdelt_data(
    query: str = "supply chain disruption",
    mode: str = "timelinevolinfo",
    start_date: str | None = None,
    end_date: str | None = None,
    max_records: int = 250,
    theme: str | None = None,
    output_file: str | None = None,
) -> pl.DataFrame:
    """
    GDELT 2.0 からグローバル地政学イベント・SC断絶データを取得するわ。
    APIキー不要。
    - mode: 'timelinevolinfo' (時系列ボリューム), 'artlist' (記事一覧), 'toneChart' (感情分析)
    - theme: SCM_RISK_THEMESのエイリアスを指定すると自動でフィルタ付加
    """
    if not start_date:
        start_date = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y%m%d%H%M%S")
    else:
        start_date = start_date.replace("-", "") + "000000"
    if not end_date:
        end_date = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    else:
        end_date = end_date.replace("-", "") + "235959"

    q = query
    if theme:
        theme_code = SCM_RISK_THEMES.get(theme.lower(), theme)
        q = f'({query}) theme:{theme_code}'

    params = {
        "query": q,
        "mode": mode,
        "format": "json",
        "startdatetime": start_date,
        "enddatetime": end_date,
        "maxrecords": max_records,
    }

    print(f"Fetching GDELT: query='{q}', mode={mode}, {start_date}→{end_date}...")
    try:
        response = _get_with_retry(DOC_API, params=params, timeout=60)

        if "application/json" not in response.headers.get("Content-Type", ""):
            # GDELT が CSV/HTML を返すケース
            print("GDELT returned non-JSON. Attempting CSV parse...")
            from io import StringIO
            try:
                df = pl.read_csv(StringIO(response.text))
            except Exception:  # noqa: BLE001
                return pl.DataFrame()
        else:
            data = response.json()
            if mode == "timelinevolinfo":
                # timeline が空リスト ([]) のとき [0] が IndexError になるのを防ぐ
                timeline = data.get("timeline") or []
                rows = timeline[0].get("data", []) if timeline else []
            elif mode == "artlist":
                rows = data.get("articles", [])
            elif mode.startswith("tone"):
                rows = data.get("tonechart", [])
            else:
                rows = data.get("data", []) if isinstance(data, dict) else []

            if not rows:
                print("No GDELT data found.")
                return pl.DataFrame()
            df = pl.DataFrame(rows)

        # 標準化: 時系列のdate正規化
        if "date" in df.columns:
            df = df.with_columns(pl.col("date").cast(pl.Utf8))

        if output_file:
            print(f"Saving to {output_file}...")
            df.write_csv(output_file)

        return df
    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error: {e.response.text if e.response else str(e)}")
        return pl.DataFrame()
    except Exception as e:  # noqa: BLE001
        print(f"Error fetching GDELT data: {e}")
        return pl.DataFrame()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch geopolitical / SC disruption events from GDELT 2.0.")
    parser.add_argument("--query", default="supply chain disruption", help="Keyword query.")
    parser.add_argument("--mode", default="timelinevolinfo", help="timelinevolinfo / artlist / toneChart.")
    parser.add_argument("--start", help="Start date (YYYY-MM-DD).")
    parser.add_argument("--end", help="End date (YYYY-MM-DD).")
    parser.add_argument("--max", type=int, default=250, help="Max records.")
    parser.add_argument("--theme", help=f"Theme alias: {list(SCM_RISK_THEMES.keys())}")
    parser.add_argument("--out", help="Output CSV filename.")
    args = parser.parse_args()
    fetch_gdelt_data(
        query=args.query,
        mode=args.mode,
        start_date=args.start,
        end_date=args.end,
        max_records=args.max,
        theme=args.theme,
        output_file=args.out,
    )


if __name__ == "__main__":
    main()
