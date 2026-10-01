import argparse
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any

import polars as pl
import requests  # noqa: F401 - テストが corp_fetcher.requests.get を patch する
from dotenv import load_dotenv

from api_utils import cli_entry, require_api_key, save_output
from api_utils import get_with_retry as _get_with_retry

# Load environment variables
load_dotenv()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_page(content: bytes) -> tuple[list[dict[str, Any]], int]:
    """XML 1ページ分を (レコード一覧, 分割数 divideSize) に変換する。"""
    root = ET.fromstring(content)  # noqa: S314

    # Parse XML: each <corporation> becomes a flat dict of its child tags.
    # Namespace-agnostic ({*}) in case the response carries a default xmlns;
    # child tags are stripped of any namespace prefix.
    records: list[dict[str, Any]] = []
    for corp in root.findall(".//{*}corporation"):
        record = {_local(child.tag): (child.text or "") for child in corp}
        if record:
            records.append(record)

    divide_size = 1
    size_el = root.find("{*}divideSize")
    if size_el is not None and (size_el.text or "").strip().isdigit():
        divide_size = int(size_el.text.strip())
    return records, divide_size


def fetch_corporate_info(
    query: str, mode: str = "number", output_file: str | None = None
) -> pl.DataFrame:
    """
    Fetches corporate information from National Tax Agency Corporate Number API.
    Requirement: CORP_API_KEY in .env
    """
    api_key = require_api_key("CORP_API_KEY", "gBizINFO / 法人番号システム", "https://www.houjin-bangou.nta.go.jp/")

    # API Version 4. type=12 is the only structured format and it is XML
    # (root <corporations> with repeated <corporation> children); the API
    # offers no JSON output.
    if mode == "number":
        # Search by 13-digit corporate number
        base_url = "https://api.houjin-bangou.nta.go.jp/4/num"
        params: dict[str, Any] = {
            "id": api_key,
            "number": query,
            "type": "12",  # XML format
            "history": "0",  # No history
        }
    else:
        # Search by name
        base_url = "https://api.houjin-bangou.nta.go.jp/4/name"
        params = {
            "id": api_key,
            "name": query,
            "type": "12",  # XML format
            "mode": "2",  # Partial match
            "target": "1",  # JIS 第一・第二水準（あいまい検索）
        }

    print(f"Searching Corporate Info (Mode: {mode}, Query: {query})...")
    response = _get_with_retry(base_url, params=params, timeout=30)
    records, divide_size = _parse_page(response.content)

    # 法人名検索は 2,000 件超で応答が分割される（ヘッダーの divideSize）。
    # 仕様どおり分割番号 divide を divideSize までカウントアップして全件取得する。
    # 法人番号指定 (/num) は最大10件指定のため分割されない。
    if mode != "number":
        for divide in range(2, divide_size + 1):
            page = _get_with_retry(base_url, params={**params, "divide": str(divide)}, timeout=30)
            page_records, _ = _parse_page(page.content)
            records.extend(page_records)

    if not records:
        print("No corporate data found.")
        return pl.DataFrame()

    df = pl.DataFrame(records, infer_schema_length=None)
    save_output(df, output_file)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch Corporate Info (National Tax Agency)."
    )
    parser.add_argument("query", help="Corporate Number (13 digits) or Company Name")
    parser.add_argument(
        "--name", action="store_true", help="Search by name instead of number"
    )
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    mode = "name" if args.name else "number"
    output_file = args.out or f"corp_{urllib.parse.quote(args.query.replace(' ', '_'), safe='')}.csv"
    fetch_corporate_info(args.query, mode, output_file)


if __name__ == "__main__":
    cli_entry(main)
