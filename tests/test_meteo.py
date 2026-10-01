"""Tests for meteo_fetcher.py (Open-Meteo weather API)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest
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


MOCK_BOTH_RESPONSE = {**MOCK_HOURLY_RESPONSE, "daily": MOCK_DAILY_RESPONSE["daily"]}


@patch("meteo_fetcher.requests.get")
def test_daily_true_with_default_hourly_returns_daily(mock_get: MagicMock, make_response) -> None:
    """daily=True（hourly は既定のまま）で日次データを返す。以前は時間別が優先され日次が捨てられた。"""
    mock_get.return_value = make_response(json=MOCK_BOTH_RESPONSE)

    df = fetch_open_meteo(35.69, 139.69, daily=True)

    assert "temperature_2m_max" in df.columns
    assert df["type"].unique().to_list() == ["daily"]
    params = mock_get.call_args[1]["params"]
    assert "daily" in params
    assert "hourly" not in params


@patch("meteo_fetcher.requests.get")
def test_default_returns_hourly(mock_get: MagicMock, make_response) -> None:
    """既定（引数なし）は時間別データを DataFrame で返す。"""
    mock_get.return_value = make_response(json=MOCK_HOURLY_RESPONSE)

    df = fetch_open_meteo(35.69, 139.69)

    assert isinstance(df, pl.DataFrame)
    assert df.height == 2
    assert "temperature_2m" in df.columns
    assert "daily" not in mock_get.call_args[1]["params"]


def test_hourly_and_daily_both_true_raises() -> None:
    with pytest.raises(ValueError, match="同時"):
        fetch_open_meteo(35.69, 139.69, hourly=True, daily=True)


@pytest.mark.parametrize(("start", "end"), [("2024-01-01", None), (None, "2024-01-02")])
@patch("meteo_fetcher.requests.get")
def test_only_one_of_start_end_raises(mock_get: MagicMock, start, end) -> None:
    """historical で start/end の片方だけ指定は黙って無視せず ValueError（API も 400 を返す）。"""
    with pytest.raises(ValueError, match="start_date と end_date"):
        fetch_open_meteo(35.69, 139.69, historical=True, start_date=start, end_date=end)
    mock_get.assert_not_called()


@patch("meteo_fetcher.requests.get")
def test_fetch_api_error_raises(mock_get: MagicMock, tmp_path: Path) -> None:
    """接続エラーは握り潰さず送出し、ファイルも生成しない。"""
    import requests

    mock_get.side_effect = requests.exceptions.ConnectionError("Connection error")

    out = str(tmp_path / "meteo_err.csv")
    with (
        patch("api_utils.get_with_retry.retry.sleep"),
        pytest.raises(requests.exceptions.ConnectionError),
    ):
        fetch_open_meteo(35.69, 139.69, output_file=out)

    assert not Path(out).exists()


@patch("meteo_fetcher.requests.get")
def test_http_400_raises_with_reason(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(status=400, json={"error": True, "reason": "Parameter 'x' invalid"})

    with pytest.raises(RuntimeError, match="Parameter 'x' invalid"):
        fetch_open_meteo(35.69, 139.69)


@patch("meteo_fetcher.requests.get")
def test_fetch_no_hourly_or_daily_data_raises(mock_get: MagicMock, make_response, tmp_path: Path) -> None:
    """要求したセクションが応答に無いのは異常。空で返さず例外、ファイルも生成しない。"""
    mock_get.return_value = make_response(json={"current_weather": {}})

    out = str(tmp_path / "meteo_empty.csv")
    with pytest.raises(RuntimeError, match="no 'hourly'"):
        fetch_open_meteo(35.69, 139.69, output_file=out, hourly=True, daily=False)

    assert not Path(out).exists()


@patch("meteo_fetcher.requests.get")
def test_no_output_file_writes_nothing(
    mock_get: MagicMock, make_response, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_get.return_value = make_response(json=MOCK_HOURLY_RESPONSE)
    monkeypatch.chdir(tmp_path)

    fetch_open_meteo(35.69, 139.69)

    assert list(tmp_path.iterdir()) == []


@patch("meteo_fetcher.requests.get")
def test_hub_get_weather_daily(mock_get: MagicMock, make_response, hub) -> None:
    """Hub の get_weather(daily=True) が日次データを date 列付きで返す。"""
    mock_get.return_value = make_response(json=MOCK_BOTH_RESPONSE)

    df = hub.get_weather(lat=35.69, lon=139.69, daily=True)

    assert "temperature_2m_max" in df.columns
    assert df["date"].to_list() == ["2024-01-01", "2024-01-02"]
