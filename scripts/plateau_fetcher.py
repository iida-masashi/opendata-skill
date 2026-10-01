import argparse
import re
from typing import Any

import polars as pl
import requests  # noqa: F401 - テストが plateau_fetcher.requests.get を patch する

from api_utils import cli_entry, save_output
from api_utils import get_with_retry as _get_with_retry

# PLATEAU 都市別パッケージ: name="plateau-13101-chiyoda-ku-2025",
# title="3D都市モデル（Project PLATEAU）千代田区（2025年度）"
_NAME_RE = re.compile(r"^plateau-(\d{5})-.+-(\d{4})$")
_TITLE_CITY_RE = re.compile(r"）([^（）]+)（")


def _match_city(results: list[dict[str, Any]], query: str) -> dict[str, Any]:
    """検索結果から自治体名 query に一致する都市パッケージを1つ選ぶ。

    全文検索は別自治体（同名の府中市など）や部分一致も返すため、1件目を黙って採用しない。
    一致した自治体が複数コードにまたがれば曖昧として例外、同一コード内は最新年度を採る。
    """
    candidates = []
    for pkg in results:
        m = _NAME_RE.match(pkg.get("name") or "")
        if not m:
            continue  # 23区一括版・ポータル等の都市別でないパッケージ
        city = _TITLE_CITY_RE.search(pkg.get("title") or "")
        label = city.group(1) if city else None
        candidates.append((m.group(1), int(m.group(2)), label, pkg))

    matched = [c for c in candidates if c[2] == query]
    if not matched:
        found = sorted({f"{label}({code})" for code, _, label, _ in candidates})
        raise ValueError(f"PLATEAU: '{query}' に一致する自治体のデータセットがありません。候補: {found}")

    codes = {c[0] for c in matched}
    if len(codes) > 1:
        raise ValueError(
            f"PLATEAU: '{query}' に一致する同名の自治体が複数あり、このフェッチャーでは区別できません: "
            f"{sorted(codes)}"
        )
    return max(matched, key=lambda c: c[1])[3]


def fetch_plateau_model(query: str, output_file: str | None = None) -> pl.DataFrame:
    """
    Fetches PLATEAU 3D City Model metadata.
    """
    base_url = "https://www.geospatial.jp/ckan/api/3/action/package_search"

    # 自治体コード（例: 13101）は全文検索に掛からず常に0件になるため、明示的に弾く。
    if query.isdigit():
        raise ValueError("PLATEAU: 自治体コードでの検索には対応していません。自治体名（例: 千代田区）で指定してください。")

    # Construct search query
    # PLATEAU datasets usually look like "3D都市モデル（Project PLATEAU）千代田区（2025年度）"
    search_q = f"PLATEAU {query}"

    params: dict[str, Any] = {
        "q": search_q,
        "rows": 20
    }

    print(f"Searching PLATEAU dataset for: {query}...")
    response = _get_with_retry(base_url, params=params)
    data = response.json()

    if not data.get('success', True):
        raise RuntimeError(f"CKAN API error: {data.get('error')}")

    results = data.get('result', {}).get('results', [])
    if not results:
        print("No PLATEAU dataset found for this code.")
        return pl.DataFrame()

    package = _match_city(results, query)
    title = package.get('title')
    resources = package.get('resources', [])

    print(f"Found Dataset: {title}")

    # Filter for interesting resources (e.g., '3D Tiles', 'GeoJSON', 'CityGML')
    # Use Case: "Flood Risk" -> 'disaster_risk'?
    # Let's list available resources and maybe download a small one (like Dictionary or Metadata)  # noqa: E501
    # or just output the URLs to a CSV so the user can download manually.

    resource_list = []
    for res in resources:
        resource_list.append({
            'name': res.get('name'),
            'format': res.get('format'),
            'url': res.get('url'),
            'description': res.get('description')
        })

    df = pl.DataFrame(resource_list)
    save_output(df, output_file)
    return df

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch PLATEAU Dataset Metadata.")
    parser.add_argument("--query", required=True, help="City Name (e.g. 千代田区)")  # noqa: E501
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    output_file = args.out or f"plateau_resources_{args.query.replace(' ', '_')}.csv"
    df = fetch_plateau_model(args.query, output_file)
    if not df.is_empty():
        print("Done. Use these URLs to download specific 3D data.")

if __name__ == "__main__":
    cli_entry(main)
