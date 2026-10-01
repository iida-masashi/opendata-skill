"""Tests for gsi_fetcher.py (国土地理院 住所検索)."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from gsi_fetcher import fetch_gsi_msearch


@patch("gsi_fetcher.requests.get")
def test_returns_dataframe(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(json=[
        {"geometry": {"coordinates": [139.74, 35.65], "type": "Point"},
         "properties": {"addressCode": "", "title": "東京タワー"}},
    ])

    df = fetch_gsi_msearch("東京タワー")

    assert df.to_dicts() == [
        {"Name": "東京タワー", "AddressCode": "", "Longitude": 139.74, "Latitude": 35.65}
    ]


@patch("gsi_fetcher.requests.get")
def test_http_error_raises(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(status=400, text="")

    with pytest.raises(requests.exceptions.HTTPError):
        fetch_gsi_msearch("x")
