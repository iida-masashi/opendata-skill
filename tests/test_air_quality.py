"""Tests for air_quality_fetcher.py (Open-Meteo Air Quality API)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest
from air_quality_fetcher import fetch_air_quality

MOCK_AQ_RESPONSE = {
    "latitude": 35.7,
    "longitude": 139.7,
    "hourly": {
        "time": ["2024-01-01T00:00", "2024-01-01T01:00"],
        "pm10": [10.0, 12.0],
        "pm2_5": [5.0, 6.0],
    },
}


@patch("air_quality_fetcher.requests.get")
def test_returns_dataframe_and_saves_csv(mock_get: MagicMock, make_response, tmp_path: Path) -> None:
    mock_get.return_value = make_response(json=MOCK_AQ_RESPONSE)
    out = tmp_path / "aq.csv"

    df = fetch_air_quality(35.7, 139.7, output_file=str(out))

    assert isinstance(df, pl.DataFrame)
    assert df.columns == ["time", "pm10", "pm2_5"]
    assert pl.read_csv(out).height == 2


@patch("air_quality_fetcher.requests.get")
def test_date_range_passed(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(json=MOCK_AQ_RESPONSE)

    fetch_air_quality(35.7, 139.7, start_date="2024-01-01", end_date="2024-01-02")

    params = mock_get.call_args[1]["params"]
    assert params["start_date"] == "2024-01-01"
    assert params["end_date"] == "2024-01-02"


@patch("air_quality_fetcher.requests.get")
def test_only_start_raises(mock_get: MagicMock) -> None:
    """start/end の片方だけは黙って無視せず ValueError。"""
    with pytest.raises(ValueError, match="start_date と end_date"):
        fetch_air_quality(35.7, 139.7, start_date="2024-01-01")
    mock_get.assert_not_called()


@patch("air_quality_fetcher.requests.get")
def test_http_error_raises(mock_get: MagicMock, make_response, tmp_path: Path) -> None:
    mock_get.return_value = make_response(status=400, json={"error": True, "reason": "Bad Request"})
    out = tmp_path / "aq.csv"

    with pytest.raises(RuntimeError, match="Bad Request"):
        fetch_air_quality(35.7, 139.7, output_file=str(out))
    assert not out.exists()


@patch("air_quality_fetcher.requests.get")
def test_missing_hourly_raises(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(json={"latitude": 35.7})

    with pytest.raises(RuntimeError, match="no 'hourly'"):
        fetch_air_quality(35.7, 139.7)


@patch("air_quality_fetcher.requests.get")
def test_no_output_file_writes_nothing(
    mock_get: MagicMock, make_response, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_get.return_value = make_response(json=MOCK_AQ_RESPONSE)
    monkeypatch.chdir(tmp_path)

    fetch_air_quality(35.7, 139.7)

    assert list(tmp_path.iterdir()) == []
