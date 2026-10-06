import argparse
import datetime
import io
import zipfile

import polars as pl
import requests
from api_utils import cli_entry, save_output
from api_utils import get_with_retry as _get_with_retry

# でんき予報「過去の電力使用実績データ <2022年4月以降>」(download_year-j.html) の月別 ZIP。
# 中身は日別 CSV (YYYYMMDD_power_usage.csv)。旧形式の年次 juyo-YYYY.csv は 2025-07-22 で更新が止まり、
# 日次の juyo-d-j.csv は 404 になった。
TEPCO_ZIP_URL = "https://www.tepco.co.jp/forecast/html/images/{ym}_power_usage.zip"


def _read_hourly_section(text: str, name: str) -> pl.DataFrame:
    """日別 CSV から1時間値の表（"DATE,TIME,当日実績(万kW),..." から空行まで）を取り出す。

    日別 CSV はピーク時供給力・予想最大電力・1時間値・5分間隔値などの表が空行区切りで続く。
    最初の "DATE,TIME," ヘッダが1時間値、2つ目が5分間隔値。
    """
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("DATE,TIME,")), None)
    if start is None:
        raise ValueError(f"TEPCO CSV header (DATE,TIME,...) not found in {name}. First lines: {lines[:3]}")
    end = next((i for i in range(start + 1, len(lines)) if not lines[i].strip()), len(lines))
    return pl.read_csv("\n".join(lines[start:end]).encode("utf-8"), infer_schema_length=None)


def _fetch_month(year: int, month: int) -> pl.DataFrame:
    """月別 ZIP を取得し、日別 CSV の1時間値を日付順につなげる。"""
    url = TEPCO_ZIP_URL.format(ym=f"{year}{month:02d}")
    print(f"Fetching {url}...")
    response = _get_with_retry(url)
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        names = sorted(n for n in zf.namelist() if n.endswith(".csv"))
        if not names:
            raise ValueError(f"No CSV in {url}: {zf.namelist()}")
        frames = [_read_hourly_section(zf.read(n).decode("cp932", errors="replace"), n) for n in names]
    return pl.concat(frames, how="vertical_relaxed")


def _download_current_year() -> pl.DataFrame:
    """当年1月から当月までの月別 ZIP を取る。

    当月分だけは月初にまだ公開されていないことがあるので 404 を許す。それ以外の失敗は伝播させる。
    """
    today = datetime.datetime.now().date()  # noqa: DTZ005
    frames = []
    for month in range(1, today.month + 1):
        try:
            frames.append(_fetch_month(today.year, month))
        except requests.exceptions.HTTPError as e:
            not_found = e.response is not None and e.response.status_code == 404
            if month == today.month and not_found and frames:
                print(f"⚠️ {today.year}{month:02d} is not published yet (404). Returning data up to the previous month.")
                break
            raise
    return pl.concat(frames, how="vertical_relaxed")


def fetch_power_usage(
    area: str = "tokyo", date: str | None = None, output_file: str | None = None
) -> pl.DataFrame:
    """
    Fetches electric power usage and supply/demand data (TEPCO, hourly).

    date (YYYY-MM-DD) を指定するとその月の ZIP からその日の24時間分を返す。
    省略時は当年1月から最新日までの1時間値を返す。
    列: DATE, TIME, 当日実績(万kW), 予測値(万kW), 使用率(%), 供給力(万kW)
    """

    # Map areas to endpoints (TEPCO example)
    # Note: Each power company has different URL structures.
    # We will focus on TEPCO for this MVP.

    if area.lower() != "tokyo":
        raise ValueError(
            f"Unsupported area: {area}. Currently only 'tokyo' (TEPCO) is supported in this MVP script."
        )

    if date:
        target_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()  # noqa: DTZ007
        df = _fetch_month(target_date.year, target_date.month)
        date_col = df.columns[0]
        df = df.with_columns(pl.col(date_col).str.to_date("%Y/%m/%d"))
        df = df.filter(pl.col(date_col) == target_date)

        if df.is_empty():
            print(f"No data found for date: {date}")
            return df
    else:
        df = _download_current_year()

    save_output(df, output_file)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Electric Power Usage (TEPCO).")
    parser.add_argument("--area", default="tokyo", help="Power Area (currently only 'tokyo' supported)")
    parser.add_argument("--date", help="Specific Date (YYYY-MM-DD). If omitted, fetches this year's hourly data.")
    parser.add_argument("--out", help="Output CSV filename (default: power_<area>.csv)")

    args = parser.parse_args()
    fetch_power_usage(args.area, args.date, args.out or f"power_{args.area}.csv")


if __name__ == "__main__":
    cli_entry(main)
