"""Tests for meteo_fetcher.py (Open-Meteo weather API)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from meteo_fetcher import fetch_open_meteo

MOCK_HOURLY_RESPONSE = {
    "latitude": 35.69,
    "longitude": 139.69,
    "timezone": "Asia/Tokyo",
    "current_weather": {"temperature": 20.5, "windspeed": 10.0, "weathercode": 1},
    "hourly": {
        "time": ["2024-01-01T00:00", "2024-01-01T01:00"],
        "temperature_2m": [10.0, 11.0],
        "relative_humidity_2m": [60, 62],
        "precipitation": [0.0, 0.1],
        "rain": [0.0, 0.0],
        "showers": [0.0, 0.0],
        "snowfall": [0.0, 0.0],
        "weathercode": [1, 2],
        "cloudcover": [20, 30],
        "windspeed_10m": [5.0, 6.0],
    },
}

MOCK_DAILY_RESPONSE = {
    "latitude": 35.69,
    "longitude": 139.69,
    "timezone": "Asia/Tokyo",
    "current_weather": {"temperature": 20.5},
    "daily": {
        "time": ["2024-01-01", "2024-01-02"],
        "temperature_2m_max": [15.0, 16.0],
        "temperature_2m_min": [5.0, 6.0],
        "precipitation_sum": [0.0, 1.0],
        "rain_sum": [0.0, 0.5],
        "showers_sum": [0.0, 0.0],
        "snowfall_sum": [0.0, 0.0],
        "weathercode": [1, 3],
        "windspeed_10m_max": [10.0, 12.0],
    },
}


@patch("meteo_fetcher.requests.get")
def test_fetch_hourly_saves_csv(mock_get: MagicMock, tmp_path: Path) -> None:
    """正常系: hourlyデータを取得してCSVに保存する。"""
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_HOURLY_RESPONSE
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    out = str(tmp_path / "meteo_test.csv")
    fetch_open_meteo(35.69, 139.69, output_file=out, hourly=True, daily=False)

    assert Path(out).exists()
    content = Path(out).read_text()
    assert "temperature_2m" in content
    assert "2024-01-01T00:00" in content


@patch("meteo_fetcher.requests.get")
def test_fetch_daily_saves_csv(mock_get: MagicMock, tmp_path: Path) -> None:
    """正常系: dailyデータを取得してCSVに保存する。"""
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_DAILY_RESPONSE
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    out = str(tmp_path / "meteo_daily.csv")
    fetch_open_meteo(35.69, 139.69, output_file=out, hourly=False, daily=True)

    assert Path(out).exists()
    content = Path(out).read_text()
    assert "temperature_2m_max" in content


@patch("meteo_fetcher.requests.get")
def test_fetch_uses_historical_url(mock_get: MagicMock, tmp_path: Path) -> None:
    """historical=Trueのときarchive APIのURLを使う。"""
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_HOURLY_RESPONSE
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    out = str(tmp_path / "meteo_hist.csv")
    fetch_open_meteo(
        35.69, 139.69, output_file=out, historical=True,
        start_date="2024-01-01", end_date="2024-01-02",
    )

    called_url = mock_get.call_args[0][0]
    assert "archive-api" in called_url


@patch("meteo_fetcher.requests.get")
def test_fetch_handles_api_error(mock_get: MagicMock, tmp_path: Path) -> None:
    """APIエラー時はファイルを生成しない（クラッシュしない）。"""
    mock_get.side_effect = Exception("Connection error")

    out = str(tmp_path / "meteo_err.csv")
    fetch_open_meteo(35.69, 139.69, output_file=out)

    assert not Path(out).exists()


@patch("meteo_fetcher.requests.get")
def test_fetch_no_hourly_or_daily_data(mock_get: MagicMock, tmp_path: Path) -> None:
    """hourly/dailyデータがない場合はファイルを生成しない。"""
    mock_response = MagicMock()
    mock_response.json.return_value = {"current_weather": {}}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    out = str(tmp_path / "meteo_empty.csv")
    fetch_open_meteo(35.69, 139.69, output_file=out, hourly=True, daily=False)

    assert not Path(out).exists()
