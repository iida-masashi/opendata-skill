"""Tests for usgs_fetcher.py (USGS Earthquake - APIキー不要、実API)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from usgs_fetcher import fetch_usgs_earthquakes


@pytest.mark.integration
def test_real_api_fetch(tmp_path: Path) -> None:
    """実API: 直近30日のM>=5地震を取得。USGSは常にデータあり。"""
    out = str(tmp_path / "usgs_real.csv")
    df = fetch_usgs_earthquakes(min_magnitude=5.0, output_file=out)
    assert isinstance(df, pl.DataFrame)
    # 地球上でM5以上は直近30日で必ず数件発生している
    assert df.height > 0
    assert "magnitude" in df.columns
    assert "latitude" in df.columns
    assert "longitude" in df.columns
    assert Path(out).exists()


@pytest.mark.integration
def test_real_api_bbox_japan() -> None:
    """実API: bbox指定で日本近海に限定できる。"""
    df = fetch_usgs_earthquakes(
        min_magnitude=3.0,
        min_lat=24, max_lat=46,
        min_lon=123, max_lon=146,
    )
    assert isinstance(df, pl.DataFrame)
    if df.height > 0:
        # 緯度が範囲内にあることを検証
        lats = df.get_column("latitude").to_list()
        for lat in lats:
            if lat is not None:
                assert 24 <= lat <= 46


@patch("usgs_fetcher.requests.get")
def test_mock_geojson_parse(mock_get: MagicMock, tmp_path: Path) -> None:
    """モック: GeoJSON レスポンスから地震リストをパース。"""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "features": [
            {
                "properties": {
                    "mag": 6.1,
                    "place": "Offshore Japan",
                    "time": 1735689600000,
                    "tsunami": 0,
                    "sig": 573,
                    "type": "earthquake",
                    "url": "https://example.com/eq1",
                },
                "geometry": {"coordinates": [140.5, 35.2, 30.0]},
            },
            {
                "properties": {
                    "mag": 5.4,
                    "place": "Chile",
                    "time": 1735776000000,
                    "tsunami": 0,
                    "sig": 450,
                    "type": "earthquake",
                    "url": "https://example.com/eq2",
                },
                "geometry": {"coordinates": [-70.5, -30.0, 50.0]},
            },
        ]
    }
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    out = str(tmp_path / "usgs_mock.csv")
    df = fetch_usgs_earthquakes(min_magnitude=5.0, output_file=out)
    assert df.height == 2
    assert df.get_column("magnitude").to_list() == [6.1, 5.4]


@patch("usgs_fetcher.requests.get")
def test_mock_empty_result(mock_get: MagicMock) -> None:
    """空のfeaturesでクラッシュしない。"""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"features": []}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    df = fetch_usgs_earthquakes(min_magnitude=9.0)
    assert df.is_empty()


@patch("usgs_fetcher.requests.get")
def test_mock_http_error(mock_get: MagicMock) -> None:
    """HTTPエラー時にクラッシュしない。"""
    import requests
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=MagicMock(text="err"))
    mock_get.return_value = mock_resp

    df = fetch_usgs_earthquakes()
    assert df.is_empty()
