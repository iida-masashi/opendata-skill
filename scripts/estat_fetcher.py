import argparse
import os
from typing import Any

import polars as pl
import requests  # noqa: F401 - テストが estat_fetcher.requests.get を patch する
from api_utils import cli_entry, rate_limited, require_api_key, save_output
from api_utils import get_with_retry as _get_with_retry
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# RESULT.STATUS: 0=正常終了, 1=正常終了・該当データ無し, 2=正常終了・一括取得の一部リクエストで該当データ無し,
# 100以上=エラー (e-Stat API 仕様 3.0)
_ESTAT_NO_DATA_STATUSES = {1, 2}

# 需要予測・S&OP 向け主要統計の statsDataId プリセット辞書
ESTAT_PRESETS: dict[str, str] = {
    "population": "0003448237",             # 人口推計（各月1日現在人口）
    "cpi": "0003427113",                    # 2020年基準消費者物価指数（全国・月次）
    "keiki_di": "0003446461",               # 景気動向指数（CI/DI・月次）
    "labor_force": "0003005798",            # 労働力調査（基本集計・全国月次）
    "inbound_visitors": "0003449064",       # 訪日外客統計（国籍・月別訪日外客数）
    "retail_sales": "0003355268",           # 商業動態統計（業態別・商品別販売額・月次）
    "industrial_production": "0003335036",  # 鉱工業指数（生産・出荷・在庫指数・月次）
    "housing_starts": "0003103532",         # 建築着工統計調査（新設住宅着工戸数・月次）
    "economy_watchers": "0003348423",       # 景気ウォッチャー調査（現状・先行き判断DI・月次）
    "household_spending": "0003343671",     # 家計調査（二人以上の世帯・品目分類別支出・月次）
    "monthly_wages": "0003318162",          # 毎月勤労統計調査（全国調査・現金給与総額・実質賃金指数）
}



def check_estat_result(section: dict[str, Any]) -> bool:
    """e-Stat 応答の RESULT.STATUS を検査する。

    section は GET_STATS_DATA / GET_STATS_LIST 等のルート直下の dict。
    正常でデータ有りなら True、正常終了だが該当データ無しなら False、エラーなら RuntimeError。
    """
    result = section["RESULT"]
    status = int(result["STATUS"])
    if status == 0:
        return True
    if status in _ESTAT_NO_DATA_STATUSES:
        return False
    raise RuntimeError(f"e-Stat API error (STATUS={status}): {result.get('ERROR_MSG')}")


def as_list(obj: Any) -> list[Any]:
    """e-Stat JSON は要素が1件だと配列でなく dict で返るため、常に list にそろえる。"""
    if obj is None:
        return []
    if isinstance(obj, dict):
        return [obj]
    return obj


@rate_limited(max_calls=2, period=1.0)
def fetch_estat_data(
    app_id: str, stats_data_id: str, output_file: str | None = None, **kwargs: Any
) -> pl.DataFrame:
    """
    Fetches statistical data from e-Stat API and returns it as a Polars DataFrame.
    Accepts additional kwargs like cdArea, cdCat01 for advanced filtering.
    output_file を指定すると CSV にも保存する。
    """
    base_url = "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData"
    resolved_id = ESTAT_PRESETS.get(stats_data_id, stats_data_id)
    params: dict[str, Any] = {
        "appId": app_id,
        "statsDataId": resolved_id,
        "metaGetFlg": "Y",
        "cntGetFlg": "N",
        "sectionHeaderFlg": "1",
    }
    if kwargs:
        params.update(kwargs)

    print(f"Fetching data for StatsDataId: {resolved_id}...")
    all_data_objects: list[dict[str, Any]] = []
    note_chars: set[str] = set()
    class_map: dict[str, dict[str, Any]] = {}

    while True:
        data = _get_with_retry(base_url, params=params).json()

        if not check_estat_result(data["GET_STATS_DATA"]):
            if not all_data_objects:
                print("No data (e-Stat returned STATUS: no matching data).")
                return pl.DataFrame()
            break

        statistical_data = data["GET_STATS_DATA"]["STATISTICAL_DATA"]
        if "DATA_INF" not in statistical_data:
            raise RuntimeError(
                f"e-Stat response has no DATA_INF despite STATUS=0 "
                f"(keys: {list(statistical_data.keys())})"
            )

        # Process Class Objects (Metadata for labels)
        if not class_map:
            class_objects = as_list(statistical_data.get("CLASS_INF", {}).get("CLASS_OBJ", []))
            for class_obj in class_objects:
                class_id = class_obj["@id"]
                class_name = class_obj["@name"]
                objects = as_list(class_obj.get("CLASS", []))
                mapping = {obj["@code"]: obj["@name"] for obj in objects}
                class_map[class_id] = {"name": class_name, "mapping": mapping}

        # Process Data Objects
        data_inf = statistical_data.get("DATA_INF", {})
        note_chars.update(
            n["@char"] for n in as_list(data_inf.get("NOTE", [])) if "@char" in n
        )

        # Try DATA_OBJ first, then VALUE
        page_objects = data_inf.get("DATA_OBJ", [])
        if not page_objects:
            page_objects = data_inf.get("VALUE", [])
        all_data_objects.extend(as_list(page_objects))

        next_key = statistical_data.get("RESULT_INF", {}).get("NEXT_KEY")
        if next_key:
            params = {**params, "startPosition": str(next_key)}
        else:
            break

    data_objects = all_data_objects
    if not data_objects:
        print("No data found in DATA_OBJ or VALUE.")
        return pl.DataFrame()

    print(f"Debug: Found {len(data_objects)} items (DATA_OBJ or VALUE)")

    records: list[dict[str, Any]] = []
    for item in data_objects:
        record: dict[str, Any] = {}
        for key, value in item.items():
            # Map keys to human readable names if possible, else keep code
            if key.startswith("@"):
                clean_key = key[1:]  # remove @
                if clean_key in class_map:
                    # Map value code to name
                    mapped_value = class_map[clean_key]["mapping"].get(value, value)
                    col_name = class_map[clean_key]["name"]
                    record[col_name] = mapped_value
                elif clean_key == "unit":
                    record["unit"] = value
                else:
                    record[clean_key] = value
            elif key == "$":
                # 観測値。下の Value handling で 'value' 列として扱うので
                # ここで重複した '$' 列を作らない。
                continue
            else:
                record[key] = value

        # Value handling
        if "$" in item:
            if item["$"] in note_chars:
                record["value"] = None
                record["value_note"] = item["$"]
            else:
                record["value"] = item["$"]

        records.append(record)

    # キーが行ごとに揃わない（value_note 等）ため、全行でスキーマを推論する
    df = pl.DataFrame(records, infer_schema_length=None)

    # Date Formatting
    time_col = None
    for col in df.columns:
        if "時間" in col or col.lower() == "time" or "Time" in col or "Year" in col:
            time_col = col
            break

    if time_col:
        print(f"Formatting date column: {time_col}")

        df = df.with_columns(
            pl.col(time_col).map_elements(format_estat_date, return_dtype=pl.String)
        )

        # Hub の date 正規化は列名 date/time/時間 の完全一致のみ。'時間軸（年次）' 等は
        # 乗らないので、時間列の写しを date 列として先頭に足す（元の列は残す）。
        if not any(c.lower() in ("date", "time", "時間") for c in df.columns):
            df = df.select(pl.col(time_col).alias("date"), pl.all())

    save_output(df, output_file)
    return df


def format_estat_date(val: Any) -> Any:
    """e-Stat の時間コード（10桁: YYYYPPSSSS、または YYYY / YYYYMM / YYYYMMDD）を YYYYMMDD 文字列へ正規化する。"""
    s_val = str(val)
    if not s_val.isdigit():
        return val
    if len(s_val) == 10:
        # e-Stat 10桁時間コード: YYYY (0..4) + 期別フラグ (4..6: 00=暦年/月/四半期, 10=年度等) + 開始月 (6..8) + 終了月 (8..10)
        year = s_val[:4]
        m_part = s_val[6:8]
        month = m_part if 1 <= int(m_part) <= 12 else "01"
        return f"{year}{month}01"
    if len(s_val) >= 4:
        year = s_val[:4]
        month = "01"
        day = "01"
        if len(s_val) >= 6 and 1 <= int(s_val[4:6]) <= 12:
            month = s_val[4:6]
        if len(s_val) >= 8 and 1 <= int(s_val[6:8]) <= 31:
            day = s_val[6:8]
        return f"{year}{month}{day}"
    return val


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch e-Stat data and save as CSV.")
    parser.add_argument(
        "--appId",
        help="e-Stat Application ID (default: env ESTAT_API_KEY)",
        default=os.getenv("ESTAT_API_KEY"),
    )
    parser.add_argument("--statsDataId", required=True, help="Statistics Data ID")
    parser.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Additional API filter, e.g. --param cdArea=13000 --param cdCat01=001 (repeatable)",
    )
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()

    app_id = args.appId or require_api_key("ESTAT_API_KEY", "e-Stat", "https://www.e-stat.go.jp/api/")

    extra: dict[str, str] = {}
    for kv in args.param:
        if "=" not in kv:
            parser.error(f"--param must be KEY=VALUE, got: {kv}")
        k, v = kv.split("=", 1)
        extra[k] = v

    fetch_estat_data(app_id, args.statsDataId, args.out or f"estat_data_{args.statsDataId}.csv", **extra)


if __name__ == "__main__":
    cli_entry(main)
