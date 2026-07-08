import sys
from pathlib import Path
from typing import Any

import polars as pl
from dotenv import load_dotenv
from edinetdb import client as edinet_client

# 環境変数を読み込む
load_dotenv()

# 動的ロード対応
scripts_dir = Path(__file__).resolve().parent
if str(scripts_dir) not in sys.path:
    sys.path.append(str(scripts_dir))


def fetch_edinet_financials(
    edinet_code: str,
    period: str = "annual",
    years: int | None = None,
    output_file: str | None = None,
    **kwargs: Any
) -> None:
    """
    EDINET DBから財務データを取得してCSVに保存するわ。

    Args:
        edinet_code: EDINETコード (例: E02144)
        period: 'annual' または 'quarterly'
        years: 取得する年数 (Noneの場合はすべて)
        output_file: 保存先CSVファイルパス
    """
    params: dict[str, Any] = {"period": period}
    if years is not None:
        params["years"] = years

    client = edinet_client.Client()
    response = client.get(f"/companies/{edinet_code}/financials", params=params)

    data = response.data
    if not data:
        print(f"⚠️ No financial data found for {edinet_code}")
        df = pl.DataFrame()
    else:
        df = pl.DataFrame(data)

    if output_file:
        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.write_csv(out_path)
        print(f"✅ EDINET financials saved to {out_path} (Rows: {len(df)})")
    else:
        print(df)

def fetch_edinet_ratios(
    edinet_code: str,
    output_file: str | None = None,
    **kwargs: Any
) -> None:
    """
    EDINET DBから財務比率データを取得してCSVに保存するわ。
    """
    client = edinet_client.Client()
    response = client.get(f"/companies/{edinet_code}/ratios")

    data = response.data
    if not data:
        print(f"⚠️ No ratio data found for {edinet_code}")
        df = pl.DataFrame()
    else:
        df = pl.DataFrame(data)

    if output_file:
        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.write_csv(out_path)
        print(f"✅ EDINET ratios saved to {out_path} (Rows: {len(df)})")
    else:
        print(df)
