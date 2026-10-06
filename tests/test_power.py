"""Tests for power_fetcher.py (TEPCO でんき予報 月別 ZIP)."""
import datetime
import io
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest
import requests
from power_fetcher import fetch_power_usage

TODAY = datetime.datetime.now().date()  # noqa: DTZ005 - フェッチャーと同じ日付の決め方


def _daily_csv(day: datetime.date) -> bytes:
    """実ファイル (20260901_power_usage.csv, 2026-10 取得) と同じ並び: 更新時刻・ピーク表・空行・
    1時間値・空行・5分間隔値。1時間値は2行だけにしている。"""
    d = f"{day.year}/{day.month}/{day.day}"
    return (
        f"{d} 23:55 UPDATE\r\n"
        "ピーク時供給力(万kW),時間帯,供給力情報更新日,供給力情報更新時刻,ピーク時予備率(%),ピーク時使用率(%)\r\n"
        "4607,13:00〜14:00,9/1,23:40,15,87\r\n"
        "\r\n"
        "DATE,TIME,当日実績(万kW),予測値(万kW),使用率(%),供給力(万kW)\r\n"
        f"{d},0:00,2597,2609,77,3359\r\n"
        f"{d},1:00,2500,2510,76,3300\r\n"
        "\r\n"
        "DATE,TIME,当日実績(５分間隔値)(万kW),太陽光発電実績(５分間隔値)(万kW),太陽光発電量(電力使用量に対する割合)(%)\r\n"
        f"{d},0:00,2600,0,0\r\n"
    ).encode("cp932")


def _month_zip(year: int, month: int, days: int = 2) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        # 日付の逆順で入れても日付順に並べ直すことを確かめる
        for day in range(days, 0, -1):
            date = datetime.date(year, month, day)
            zf.writestr(f"{date:%Y%m%d}_power_usage.csv", _daily_csv(date))
    return buf.getvalue()


def _router(make_response, statuses: dict[str, int]):
    """URL の末尾ファイル名（YYYYMM_power_usage.zip）ごとにステータスを返す requests.get の代役。"""
    def _get(url: str, **_kw):
        name = url.rsplit("/", 1)[-1]
        status = statuses.get(name, 404)
        if status != 200:
            return make_response(content=b"Not Found", status=status, url=url)
        ym = name.split("_", 1)[0]
        return make_response(content=_month_zip(int(ym[:4]), int(ym[4:])), status=200, url=url)
    return _get


def _zip_name(year: int, month: int) -> str:
    return f"{year}{month:02d}_power_usage.zip"


def _all_months_ok() -> dict[str, int]:
    return {_zip_name(TODAY.year, m): 200 for m in range(1, TODAY.month + 1)}


def test_unsupported_area_raises() -> None:
    with pytest.raises(ValueError, match="tokyo"):
        fetch_power_usage(area="kansai")


@patch("power_fetcher.requests.get")
def test_returns_dataframe_without_writing_file(
    mock_get: MagicMock, make_response, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """output_file 未指定なら DataFrame を返し、勝手に CSV を書かない（Hub 経由の前提）。"""
    monkeypatch.chdir(tmp_path)
    mock_get.side_effect = _router(make_response, _all_months_ok())

    df = fetch_power_usage(area="tokyo")
    assert isinstance(df, pl.DataFrame)
    assert df.height == TODAY.month * 2 * 2  # 月数 × 2日 × 2時間
    assert list(tmp_path.iterdir()) == []
    assert mock_get.call_args_list[0][1]["timeout"] > 0


@patch("power_fetcher.requests.get")
def test_reads_only_hourly_section_in_date_order(mock_get: MagicMock, make_response) -> None:
    """ピーク表や5分間隔値を混ぜず、1時間値の表だけを日付順に読む。"""
    mock_get.side_effect = _router(make_response, _all_months_ok())

    df = fetch_power_usage(area="tokyo")
    assert df.columns == ["DATE", "TIME", "当日実績(万kW)", "予測値(万kW)", "使用率(%)", "供給力(万kW)"]
    assert df["DATE"][:4].to_list() == [f"{TODAY.year}/1/1"] * 2 + [f"{TODAY.year}/1/2"] * 2
    assert df["当日実績(万kW)"][:2].to_list() == [2597, 2500]


@patch("power_fetcher.requests.get")
def test_current_month_404_returns_up_to_previous_month(
    mock_get: MagicMock, make_response, tmp_path: Path
) -> None:
    """当月の ZIP が未公開（404）なら前月までを返す。"""
    if TODAY.month == 1:
        pytest.skip("1月は前月分が当年に無い")
    statuses = _all_months_ok()
    statuses[_zip_name(TODAY.year, TODAY.month)] = 404
    mock_get.side_effect = _router(make_response, statuses)
    out = tmp_path / "power.csv"

    df = fetch_power_usage(area="tokyo", output_file=str(out))
    assert df.height == (TODAY.month - 1) * 2 * 2
    assert out.exists()


@patch("power_fetcher.requests.get")
def test_past_month_404_raises(mock_get: MagicMock, make_response) -> None:
    """当月以外の欠落は、それより前の月が取れていても黙って飛ばさず例外。"""
    if TODAY.month < 3:
        pytest.skip("前月より前に取得済みの月が必要")
    statuses = _all_months_ok()
    statuses[_zip_name(TODAY.year, TODAY.month - 1)] = 404
    mock_get.side_effect = _router(make_response, statuses)

    with pytest.raises(requests.exceptions.HTTPError):
        fetch_power_usage(area="tokyo")


@patch("power_fetcher.requests.get")
def test_server_error_is_not_skipped(mock_get: MagicMock, make_response) -> None:
    """当月でも 404 以外（5xx 等）は前月までで黙って返さず例外。"""
    statuses = _all_months_ok()
    statuses[_zip_name(TODAY.year, TODAY.month)] = 503
    mock_get.side_effect = _router(make_response, statuses)

    with pytest.raises(requests.exceptions.HTTPError):
        fetch_power_usage(area="tokyo")


@patch("power_fetcher.requests.get")
def test_date_filter_fetches_that_month_only(mock_get: MagicMock, make_response) -> None:
    mock_get.side_effect = _router(make_response, {_zip_name(2025, 3): 200})

    df = fetch_power_usage(area="tokyo", date="2025-03-02")
    assert df.height == 2
    assert df.item(0, "DATE") == datetime.date(2025, 3, 2)
    assert df.item(1, "当日実績(万kW)") == 2500
    assert [c[0][0].rsplit("/", 1)[-1] for c in mock_get.call_args_list] == [_zip_name(2025, 3)]


@patch("power_fetcher.requests.get")
def test_date_in_missing_month_raises(mock_get: MagicMock, make_response) -> None:
    mock_get.side_effect = _router(make_response, {})

    with pytest.raises(requests.exceptions.HTTPError):
        fetch_power_usage(area="tokyo", date="2021-03-02")


@pytest.mark.integration
def test_real_tepco_zip_layout() -> None:
    """実ファイル: 月別 ZIP の日別 CSV から1時間値（1日24行）が読める。"""
    df = fetch_power_usage(area="tokyo", date="2026-09-15")
    assert df.height == 24
    assert df.columns[:3] == ["DATE", "TIME", "当日実績(万kW)"]
    assert df["当日実績(万kW)"].null_count() == 0
