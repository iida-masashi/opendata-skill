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

_PREF_TO_CODE: dict[str, str] = {
    "北海道": "01", "青森県": "02", "岩手県": "03", "宮城県": "04", "秋田県": "05",
    "山形県": "06", "福島県": "07", "茨城県": "08", "栃木県": "09", "群馬県": "10",
    "埼玉県": "11", "千葉県": "12", "東京都": "13", "神奈川県": "14", "新潟県": "15",
    "富山県": "16", "石川県": "17", "福井県": "18", "山梨県": "19", "長野県": "20",
    "岐阜県": "21", "静岡県": "22", "愛知県": "23", "三重県": "24", "滋賀県": "25",
    "京都府": "26", "大阪府": "27", "兵庫県": "28", "奈良県": "29", "和歌山県": "30",
    "鳥取県": "31", "島根県": "32", "岡山県": "33", "広島県": "34", "山口県": "35",
    "徳島県": "36", "香川県": "37", "愛媛県": "38", "高知県": "39", "福岡県": "40",
    "佐賀県": "41", "長崎県": "42", "熊本県": "43", "大分県": "44", "宮崎県": "45",
    "鹿児島県": "46", "沖縄県": "47",
}
_CODE_TO_PREF: dict[str, str] = {v: k for k, v in _PREF_TO_CODE.items()}
_PREF_SPLIT_RE = re.compile(
    r"^(" + "|".join(_PREF_TO_CODE.keys()) + r")[\s_　]*(.+)$"
)


def _normalize_city_code(code: str | None) -> str | None:
    """5桁または6桁（チェックディジット付き）の全国地方公共団体コードを5桁に正規化する。"""
    if code is None:
        return None
    cleaned = code.strip()
    if not re.fullmatch(r"\d{5,6}", cleaned):
        raise ValueError(
            f"PLATEAU: 自治体コードは5桁または6桁の数字で指定してください（指定値: '{code}'）。"
        )
    return cleaned[:5]


def _split_prefecture(query: str) -> tuple[str | None, str]:
    """'東京都府中市' のような入力を (都道府県コード '13', 自治体名 '府中市') に分解する。"""
    m = _PREF_SPLIT_RE.match(query.strip())
    if m:
        pref_name, city_name = m.group(1), m.group(2).strip()
        return _PREF_TO_CODE[pref_name], city_name
    return None, query.strip()


def _match_city(
    results: list[dict[str, Any]],
    city_query: str,
    *,
    pref_code: str | None = None,
    city_code: str | None = None,
) -> dict[str, Any]:
    """検索結果から自治体名 city_query（および任意の都道府県/自治体コード）に一致する都市パッケージを1つ選ぶ。

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

    matched = [c for c in candidates if c[2] == city_query]
    if pref_code is not None:
        matched = [c for c in matched if c[0].startswith(pref_code)]
    if city_code is not None:
        matched = [c for c in matched if c[0] == city_code]

    if not matched:
        found = sorted({
            f"{_CODE_TO_PREF.get(code[:2], '')}{label}({code})"
            for code, _, label, _ in candidates
        })
        raise ValueError(
            f"PLATEAU: '{city_query}' に一致する自治体のデータセットがありません。候補: {found}"
        )

    codes = {c[0] for c in matched}
    if len(codes) > 1:
        hints = [f"{_CODE_TO_PREF.get(c[:2], '')}{city_query}({c})" for c in sorted(codes)]
        raise ValueError(
            f"PLATEAU: '{city_query}' に一致する同名の自治体が複数あります。"
            f"都道府県名を併記（例: '{_CODE_TO_PREF.get(sorted(codes)[0][:2], '')}{city_query}'）"
            f"するか code 引数を指定してください: {hints}"
        )
    return max(matched, key=lambda c: c[1])[3]


def fetch_plateau_model(
    query: str,
    output_file: str | None = None,
    code: str | None = None,
) -> pl.DataFrame:
    """
    Fetches PLATEAU 3D City Model metadata.

    Args:
        query: 自治体名（例: '千代田区', '東京都府中市', '広島県府中市'）
        output_file: 保存先CSVファイルパス（指定時のみ保存）
        code: 全国地方公共団体コード 5桁または6桁（例: '13206' / '34208'）。同名自治体の区別に使用。
    """
    base_url = "https://www.geospatial.jp/ckan/api/3/action/package_search"

    # 自治体コード単体（例: 13101）は CKAN 全文検索に掛からず常に0件になるため、明示的に弾く。
    if query.strip().isdigit():
        raise ValueError(
            "PLATEAU: 自治体コード単体での検索には対応していません。"
            "自治体名（例: '千代田区'、'東京都府中市'）または query='府中市', code='13206' で指定してください。"
        )

    norm_code = _normalize_city_code(code)
    pref_code, city_query = _split_prefecture(query)

    # CKAN 全文検索は title に都道府県名を含まないため、検索クエリには自治体名のみを使う
    search_q = f"PLATEAU {city_query}"

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

    package = _match_city(results, city_query, pref_code=pref_code, city_code=norm_code)
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
    parser.add_argument("--query", required=True, help="City Name (e.g. 千代田区, 東京都府中市)")
    parser.add_argument("--code", help="5 or 6 digit municipal code (e.g. 13206) to disambiguate same-name cities")
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    output_file = args.out or f"plateau_resources_{args.query.replace(' ', '_')}.csv"
    df = fetch_plateau_model(args.query, output_file, code=args.code)
    if not df.is_empty():
        print("Done. Use these URLs to download specific 3D data.")

if __name__ == "__main__":
    cli_entry(main)
