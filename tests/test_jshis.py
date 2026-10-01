"""Tests for jshis_fetcher.py (J-SHIS 地震ハザード)."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from jshis_fetcher import fetch_jshis_risk


@patch("jshis_fetcher.requests.get")
def test_returns_dataframe_without_output_file(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(json={"features": [{"properties": {
        "meshcode": "5339", "T30_I45_PS": "0.9", "T30_I50_PS": "0.8",
        "T30_I55_PS": "0.4", "T30_I60_PS": "0.1",
    }}]})

    df = fetch_jshis_risk(35.0, 139.0)

    assert df["MeshCode"].to_list() == ["5339"]
    assert mock_get.call_args[1]["timeout"]  # タイムアウトが付いている


@patch("api_utils.get_with_retry.retry.sleep")
@patch("jshis_fetcher.requests.get")
def test_server_error_raises(mock_get: MagicMock, _sleep: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(status=503, text="")

    with pytest.raises(requests.exceptions.HTTPError):
        fetch_jshis_risk(35.0, 139.0)
