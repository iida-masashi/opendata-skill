"""Tests for river_fetcher.py (Open-Meteo Flood API)."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from river_fetcher import fetch_river_discharge


@patch("river_fetcher.requests.get")
def test_returns_dataframe_and_passes_dates(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(json={"daily": {
        "time": ["2024-01-01", "2024-01-02"], "river_discharge": [1.5, 2.0],
    }})

    df = fetch_river_discharge(35.0, 139.0, start_date="2024-01-01", end_date="2024-01-02")

    assert df["river_discharge"].to_list() == [1.5, 2.0]
    params = mock_get.call_args[1]["params"]
    assert params["start_date"] == "2024-01-01"
    assert params["end_date"] == "2024-01-02"


@pytest.mark.parametrize("start,end", [("2024-01-01", None), (None, "2024-01-02")])
def test_only_one_of_start_end_raises(start: str | None, end: str | None) -> None:
    """片方だけ指定すると黙って無視されていた。"""
    with pytest.raises(ValueError, match="start_date"):
        fetch_river_discharge(35.0, 139.0, start_date=start, end_date=end)


@patch("river_fetcher.requests.get")
def test_http_error_raises(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(status=400, json={"error": True, "reason": "bad"})

    with pytest.raises(requests.exceptions.HTTPError):
        fetch_river_discharge(35.0, 139.0)
