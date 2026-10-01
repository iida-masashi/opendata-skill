"""Tests for events_fetcher.py (Nager.Date 祝日)."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from events_fetcher import fetch_events_data


@patch("events_fetcher.requests.get")
def test_returns_dataframe(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(json=[
        {"date": "2024-01-01", "localName": "元日", "name": "New Year's Day"},
    ])

    df = fetch_events_data(2024, "JP")

    assert df.to_dicts() == [
        {"date": "2024-01-01", "event_name": "元日", "is_holiday": 1, "event_type": "Public Holiday"}
    ]


@patch("events_fetcher.requests.get")
def test_http_error_raises(mock_get: MagicMock, make_response) -> None:
    """国コード誤り等の 404 が空DFに化けていた。"""
    mock_get.return_value = make_response(status=404, text="")

    with pytest.raises(requests.exceptions.HTTPError):
        fetch_events_data(2024, "XX")


@patch("events_fetcher.requests.get")
def test_unexpected_payload_raises(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(json=[{"date": "2024-01-01"}])

    with pytest.raises(KeyError):
        fetch_events_data(2024, "JP")
