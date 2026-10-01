"""Tests for holiday_fetcher.py (内閣府 祝日CSV)."""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
import requests

from holiday_fetcher import fetch_japan_holidays

CSV = "国民の祝日・休日月日,国民の祝日・休日名称\r\n2024/2/11,建国記念の日\r\n2024/1/1,元日\r\n"


@patch("holiday_fetcher.requests.get")
def test_returns_sorted_dataframe(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(content=CSV.encode("shift_jis"))

    df = fetch_japan_holidays()

    assert df.columns == ["Date", "Name"]
    assert df["Date"].to_list() == [date(2024, 1, 1), date(2024, 2, 11)]
    assert df["Name"].to_list() == ["元日", "建国記念の日"]


@patch("holiday_fetcher.requests.get")
def test_http_error_raises(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(status=404, text="")

    with pytest.raises(requests.exceptions.HTTPError):
        fetch_japan_holidays()
