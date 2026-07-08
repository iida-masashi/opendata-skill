"""Tests for firms_fetcher.py (NASA_FIRMS_API_KEY未設定想定 → モック中心)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from firms_fetcher import RISK_REGIONS, SOURCES, fetch_firms_data


def test_regions_defined() -> None:
    for r in ["us_west", "california", "australia", "japan"]:
        assert r in RISK_REGIONS
        parts = RISK_REGIONS[r].split(",")
        assert len(parts) == 4


def test_sources_defined() -> None:
    for s in ["modis", "viirs_s", "viirs_n", "landsat"]:
        assert s in SOURCES


FIRMS_CSV_SAMPLE = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight\n"
    "38.5,-120.3,345.1,0.5,0.5,2026-04-10,1230,N,nominal,2.0NRT,295.2,42.5,D\n"
    "39.0,-121.1,355.2,0.5,0.5,2026-04-11,0115,N,high,2.0NRT,298.5,55.3,N\n"
)


@patch("firms_fetcher.requests.get")
def test_mock_firms_csv(mock_get: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """モック: FIRMS CSV レスポンスをパース。"""
    monkeypatch.setenv("NASA_FIRMS_API_KEY", "test_key_mock")

    mock_resp = MagicMock()
    mock_resp.text = FIRMS_CSV_SAMPLE
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    out = str(tmp_path / "firms.csv")
    df = fetch_firms_data(region="us_west", source="viirs_n", day_range=7, output_file=out)
    assert df.height == 2
    # 標準化カラム
    assert "date" in df.columns
    assert "value" in df.columns
    assert "region" in df.columns
    assert Path(out).exists()


@patch("firms_fetcher.requests.get")
def test_mock_invalid_response(mock_get: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    """無効なレスポンス（'Invalid MAP_KEY'等）で空DataFrame。"""
    monkeypatch.setenv("NASA_FIRMS_API_KEY", "test_key_mock")

    mock_resp = MagicMock()
    mock_resp.text = "Invalid MAP_KEY"
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    df = fetch_firms_data(region="us_west")
    assert df.is_empty()


@patch("firms_fetcher.requests.get")
def test_mock_empty_csv(mock_get: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    """空のCSV（ヘッダのみ）でクラッシュしない。"""
    monkeypatch.setenv("NASA_FIRMS_API_KEY", "test_key_mock")

    mock_resp = MagicMock()
    mock_resp.text = "latitude,longitude,bright_ti4\n"
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    df = fetch_firms_data(region="us_west")
    assert df.is_empty()


@patch("firms_fetcher.requests.get")
def test_day_range_clamp(mock_get: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    """day_range が範囲外(例: 20)の場合、7にクランプされる。"""
    monkeypatch.setenv("NASA_FIRMS_API_KEY", "test_key_mock")

    mock_resp = MagicMock()
    mock_resp.text = "latitude,longitude,bright_ti4\n"
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    fetch_firms_data(region="us_west", day_range=20)
    called_url = mock_get.call_args[0][0]
    assert called_url.endswith("/7")


@patch("firms_fetcher.requests.get")
def test_mock_http_error(mock_get: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    import requests
    monkeypatch.setenv("NASA_FIRMS_API_KEY", "test_key_mock")
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=MagicMock(text="403"))
    mock_get.return_value = mock_resp

    df = fetch_firms_data(region="california")
    assert df.is_empty()
