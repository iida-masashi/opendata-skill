"""Tests for mlit_fetcher.py (不動産情報ライブラリ XIT001)."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from mlit_fetcher import fetch_land_prices


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLIT_API_KEY", "dummy")


@patch("mlit_fetcher.requests.get")
def test_keys_beyond_first_100_records_are_kept(mock_get: MagicMock, make_response) -> None:
    """先頭100件に無いキーを持つ取引レコードも列として残る。"""
    records = [{"Type": "宅地", "TradePrice": "1000"} for _ in range(100)]
    records.append({"Type": "宅地", "TradePrice": "2000", "Remarks": "私道を含む取引"})
    mock_get.return_value = make_response(json={"status": "OK", "data": records})

    df = fetch_land_prices("2023", "13")

    assert df.height == 101
    assert df["Remarks"].to_list()[-1] == "私道を含む取引"


@patch("mlit_fetcher.requests.get")
def test_http_200_error_payload_raises(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(json={"status": "error", "message": "invalid year"})

    with pytest.raises(RuntimeError, match="invalid year"):
        fetch_land_prices("1800", "13")


@patch("mlit_fetcher.requests.get")
def test_http_error_raises(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(status=401, text='{"message":"Access denied"}')

    with pytest.raises(requests.exceptions.HTTPError):
        fetch_land_prices("2023", "13")
