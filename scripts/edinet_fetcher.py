import argparse
from typing import Any

import httpx
import polars as pl
from dotenv import load_dotenv
from edinetdb import client as edinet_client
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from api_utils import cli_entry, save_output

# 環境変数を読み込む
load_dotenv()


# edinetdb は httpx と独自例外を使うため api_utils のリトライ判定に乗らない。
# 一時的なエラー（429 / 5xx / 接続・タイムアウト）のみ再試行する。
@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type(
        (edinet_client.RateLimitError, edinet_client.ServerError, httpx.TransportError)
    ),
    reraise=True,
)
def _client_get(path: str, params: dict[str, Any] | None = None) -> edinet_client.Response:
    return edinet_client.Client().get(path, params=params)


def _fetch_edinet(
    path: str, label: str, params: dict[str, Any] | None, output_file: str | None
) -> pl.DataFrame:
    """EDINET DB の1エンドポイントを取得して DataFrame にする（financials / ratios 共通）。"""
    data = _client_get(path, params=params).data
    if not data:
        print(f"⚠️ No {label} data found ({path})")
        return pl.DataFrame()

    df = pl.DataFrame(data)
    save_output(df, output_file)
    return df


def fetch_edinet_financials(
    edinet_code: str,
    period: str = "annual",
    years: int | None = None,
    output_file: str | None = None,
) -> pl.DataFrame:
    """
    EDINET DBから財務データを取得するわ。

    Args:
        edinet_code: EDINETコード (例: E02144)
        period: 'annual' または 'quarterly'
        years: 取得する年数 (Noneの場合はすべて)
        output_file: 保存先CSVファイルパス（指定時のみ保存。0件なら書かない）
    """
    params: dict[str, Any] = {"period": period}
    if years is not None:
        params["years"] = years
    return _fetch_edinet(f"/companies/{edinet_code}/financials", "financial", params, output_file)


def fetch_edinet_ratios(
    edinet_code: str,
    output_file: str | None = None,
) -> pl.DataFrame:
    """
    EDINET DBから財務比率データを取得するわ。
    """
    return _fetch_edinet(f"/companies/{edinet_code}/ratios", "ratio", None, output_file)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch financial data from EDINET DB (edinetdb).")
    parser.add_argument("--code", required=True, help="EDINET code (e.g. E02144).")
    parser.add_argument("--kind", default="financials", choices=["financials", "ratios"])
    parser.add_argument("--period", default="annual", choices=["annual", "quarterly"], help="financials only.")
    parser.add_argument("--years", type=int, help="Number of years (financials only).")
    parser.add_argument("--out", help="Output CSV filename.")
    args = parser.parse_args()
    if args.kind == "financials":
        df = fetch_edinet_financials(args.code, period=args.period, years=args.years, output_file=args.out)
    else:
        df = fetch_edinet_ratios(args.code, output_file=args.out)
    if not args.out:
        print(df)


if __name__ == "__main__":
    cli_entry(main)
