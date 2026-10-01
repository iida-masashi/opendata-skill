"""Tests for power_fetcher.py (TEPCO でんき予報 CSV)."""
import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest
import requests

import api_utils
from power_fetcher import fetch_power_usage

Y = datetime.datetime.now().year  # noqa: DTZ005 - フェッチャーと同じ年の決め方
THIS_YEAR, LAST_YEAR = f"juyo-{Y}.csv", f"juyo-{Y - 1}.csv"

# 実ファイル (juyo-2025.csv, 2026-10 取得) の先頭: タイトル行・空行・ヘッダ行の順。
TEPCO_CSV = (
    "2025/7/22 5:40 UPDATE\r\n"
    "\r\n"
    "DATE,TIME,実績(万kW)\r\n"
    "2025/1/1,0:00,2644\r\n"
    "2025/1/2,0:00,2516\r\n"
).encode("shift_jis")


@pytest.fixture
def no_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_with_retry のバックオフ待機を0にする（tenacity.nap.sleep の patch は効かないため）。"""
    monkeypatch.setattr(api_utils.get_with_retry.retry, "sleep", lambda _s: None)


def _router(make_response, statuses: dict[str, int]):
    """URL の末尾ファイル名ごとにステータスを返す requests.get の代役。"""
    def _get(url: str, **_kw):
        name = url.rsplit("/", 1)[-1]
        status = statuses.get(name, 404)
        return make_response(content=TEPCO_CSV if status == 200 else b"Not Found", status=status, url=url)
    return _get


def test_unsupported_area_raises() -> None:
    with pytest.raises(ValueError, match="tokyo"):
        fetch_power_usage(area="kansai")


@patch("power_fetcher.requests.get")
def test_returns_dataframe_without_writing_file(
    mock_get: MagicMock, make_response, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """output_file 未指定なら DataFrame を返し、勝手に CSV を書かない（Hub 経由の前提）。"""
    monkeypatch.chdir(tmp_path)
    mock_get.side_effect = _router(make_response, {THIS_YEAR: 200, LAST_YEAR: 200})

    df = fetch_power_usage(area="tokyo")
    assert isinstance(df, pl.DataFrame)
    assert df.height == 2
    assert list(tmp_path.iterdir()) == []
    assert mock_get.call_args_list[0][1]["timeout"] > 0


@patch("power_fetcher.requests.get")
def test_falls_back_to_previous_year_only_on_404(
    mock_get: MagicMock, make_response, tmp_path: Path
) -> None:
    mock_get.side_effect = _router(make_response, {LAST_YEAR: 200})
    out = tmp_path / "power.csv"

    df = fetch_power_usage(area="tokyo", output_file=str(out))
    assert df.height == 2
    assert out.exists()
    urls = [c[0][0] for c in mock_get.call_args_list]
    assert urls[0].endswith(THIS_YEAR) and urls[1].endswith(LAST_YEAR)


@patch("power_fetcher.requests.get")
def test_server_error_is_not_silently_replaced_by_daily_csv(
    mock_get: MagicMock, make_response, no_retry_wait: None
) -> None:
    """404 以外（5xx 等）の失敗で日次 CSV に黙ってフォールバックせず例外。"""
    mock_get.side_effect = _router(make_response, {THIS_YEAR: 503, "juyo-d-j.csv": 200})

    with pytest.raises(requests.exceptions.HTTPError):
        fetch_power_usage(area="tokyo")
    assert not any(c[0][0].endswith("juyo-d-j.csv") for c in mock_get.call_args_list)


@patch("power_fetcher.requests.get")
def test_daily_fallback_when_yearly_files_missing(mock_get: MagicMock, make_response) -> None:
    mock_get.side_effect = _router(make_response, {"juyo-d-j.csv": 200})

    df = fetch_power_usage(area="tokyo")
    assert df.height == 2


@patch("power_fetcher.requests.get")
def test_all_missing_raises(mock_get: MagicMock, make_response) -> None:
    """年次・日次とも取得できなければ print して None ではなく例外。"""
    mock_get.side_effect = _router(make_response, {})

    with pytest.raises(requests.exceptions.HTTPError):
        fetch_power_usage(area="tokyo")


@pytest.mark.integration
def test_real_tepco_csv_layout() -> None:
    """実ファイル: ヘッダ行（DATE,TIME,...）が読め、データ行がある。"""
    df = fetch_power_usage(area="tokyo")
    assert df.height > 0
    assert "DATE" in df.columns[0].upper()


@patch("power_fetcher.requests.get")
def test_header_after_title_and_blank_line(mock_get: MagicMock, make_response) -> None:
    """実ファイルのレイアウト（タイトル・空行・ヘッダ）で DATE ヘッダを正しく読む。"""
    mock_get.side_effect = _router(make_response, {THIS_YEAR: 200})

    df = fetch_power_usage(area="tokyo")
    assert df.columns[:2] == ["DATE", "TIME"]
    assert df.height == 2


@patch("power_fetcher.requests.get")
def test_date_filter(mock_get: MagicMock, make_response) -> None:
    mock_get.side_effect = _router(make_response, {THIS_YEAR: 200})

    df = fetch_power_usage(area="tokyo", date="2025-01-02")
    assert df.height == 1
    assert df.item(0, "実績(万kW)") == 2516
