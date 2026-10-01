"""Tests for odpt_fetcher.py (公共交通オープンデータ)."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from odpt_fetcher import fetch_odpt_data


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ODPT_API_KEY", "dummy")


@patch("odpt_fetcher.requests.get")
def test_keys_beyond_first_100_records_are_kept(mock_get: MagicMock, make_response) -> None:
    records = [{"owl:sameAs": f"odpt.Station:X.{i}"} for i in range(100)]
    records.append({"owl:sameAs": "odpt.Station:X.100", "odpt:stationCode": "A01"})
    mock_get.return_value = make_response(json=records)

    df = fetch_odpt_data("odpt:Station")

    assert df.height == 101
    assert df["odpt:stationCode"].to_list()[-1] == "A01"


@patch("odpt_fetcher.requests.get")
def test_http_error_raises(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(status=403, text="")

    with pytest.raises(requests.exceptions.HTTPError):
        fetch_odpt_data("odpt:Station")
