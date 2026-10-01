import argparse
from typing import Any

import polars as pl
import requests  # noqa: F401 - テストが estat_id_searcher.requests.get を patch する
from dotenv import load_dotenv

from api_utils import cli_entry, require_api_key
from api_utils import get_with_retry as _get_with_retry
from estat_fetcher import as_list, check_estat_result

load_dotenv()

def search_estat_list(app_id: str, search_word: str) -> pl.DataFrame:
    """e-Stat の統計表をキーワード検索し、id / title の DataFrame を返す（該当無しは空DF）。"""
    base_url = "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsList"
    params: dict[str, Any] = {
        "appId": app_id,
        "searchWord": search_word,
        "limit": 20
    }

    print(f"Searching for: {search_word}")
    data = _get_with_retry(base_url, params=params).json()

    if not check_estat_result(data['GET_STATS_LIST']):
        print("Found 0 results.")
        return pl.DataFrame(schema={"id": pl.String, "title": pl.String})

    datalist = as_list(data['GET_STATS_LIST']['DATALIST_INF'].get('TABLE_INF', []))

    print(f"Found {len(datalist)} results:")
    print(f"{'ID':<15} | {'TITLE'}")
    print("-" * 80)
    rows = []
    for item in datalist:
        title = item['TITLE_SPEC']['TABLE_NAME']
        print(f"{item['@id']:<15} | {title}")
        rows.append({"id": item['@id'], "title": title})
    return pl.DataFrame(rows, schema={"id": pl.String, "title": pl.String})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("search_word", help="Keyword to search")
    args = parser.parse_args()

    app_id = require_api_key("ESTAT_API_KEY", "e-Stat", "https://www.e-stat.go.jp/api/")

    search_estat_list(app_id, args.search_word)


if __name__ == "__main__":
    cli_entry(main)
