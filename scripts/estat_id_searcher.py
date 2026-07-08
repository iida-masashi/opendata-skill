import argparse
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

def search_estat_list(app_id: str, search_word: str) -> None:
    base_url = "http://api.e-stat.go.jp/rest/3.0/app/json/getStatsList"
    params: dict[str, Any] = {
        "appId": app_id,
        "searchWord": search_word,
        "limit": 20
    }

    print(f"Searching for: {search_word}")
    try:
        response = requests.get(base_url, params=params)  # noqa: S113
        response.raise_for_status()
        data = response.json()
    except Exception as e:  # noqa: BLE001
        print(f"Error: {e}")
        return

    if data['GET_STATS_LIST']['RESULT']['STATUS'] != 0:
        print(f"API Error: {data['GET_STATS_LIST']['RESULT']['ERROR_MSG']}")
        return

    datalist = data['GET_STATS_LIST']['DATALIST_INF'].get('TABLE_INF', [])
    if isinstance(datalist, dict):
        datalist = [datalist]

    print(f"Found {len(datalist)} results:")
    print(f"{'ID':<15} | {'TITLE'}")
    print("-" * 80)
    for item in datalist:
        print(f"{item['@id']:<15} | {item['TITLE_SPEC']['TABLE_NAME']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("search_word", help="Keyword to search")
    args = parser.parse_args()

    try:
        from api_utils import require_api_key
    except ImportError:
        from .api_utils import require_api_key

    app_id = require_api_key("ESTAT_API_KEY", "e-Stat", "https://www.e-stat.go.jp/api/")

    search_estat_list(app_id, args.search_word)
