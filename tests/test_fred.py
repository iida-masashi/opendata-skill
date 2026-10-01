"""Tests for fred_fetcher.py (FRED API, モック)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest
import requests

from fred_fetcher import fetch_fred_alias, fetch_fred_data

_OBS = {
    "observations": [
        {"date": "2023-01-01", "value": "100.2"},
        {"date": "2023-02-01", "value": "."},
    ]
}


@pytest.fixture(autouse=True)
def _fred_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRED_API_KEY", "SECRETKEY123")


@patch("fred_fetcher.requests.get")
def test_fetch_fred_parses_and_passes_timeout(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(json=_OBS)
    df = fetch_fred_data("UNRATE", "2023-01-01", "2023-12-31")
    assert df.height == 1
    assert df["series_id"].to_list() == ["UNRATE"]
    assert mock_get.call_args.kwargs["timeout"] > 0


@patch("fred_fetcher.requests.get")
def test_fetch_fred_default_date_range(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(json=_OBS)
    fetch_fred_data("UNRATE")
    params = mock_get.call_args.kwargs["params"]
    start, end = params["observation_start"], params["observation_end"]
    assert int(end[:4]) - int(start[:4]) == 5


@patch("fred_fetcher.requests.get")
def test_fetch_fred_http_400_raises_without_leaking_key(mock_get: MagicMock, make_response) -> None:
    """4xx は空DFに化けず送出され、URL 中の api_key はメッセージに出ない。"""
    mock_get.return_value = make_response(
        json={"error_code": 400, "error_message": "Bad Request. The series does not exist."},
        status=400,
        url="https://api.stlouisfed.org/fred/series/observations?series_id=NAPM&api_key=SECRETKEY123",
    )
    with pytest.raises(requests.exceptions.HTTPError) as exc:
        fetch_fred_data("NAPM")
    assert "SECRETKEY123" not in str(exc.value)
    assert "does not exist" in str(exc.value)
    assert mock_get.call_count == 1  # 4xx はリトライしない


@patch("api_utils.get_with_retry.retry.sleep")
@patch("fred_fetcher.requests.get")
def test_fetch_fred_5xx_retried_then_raised(mock_get: MagicMock, _sleep: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(status=503)
    with pytest.raises(requests.exceptions.HTTPError):
        fetch_fred_data("UNRATE")
    assert mock_get.call_count == 5


@patch("fred_fetcher.requests.get")
def test_fetch_fred_error_payload_with_200_raises(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(json={"error_code": 400, "error_message": "bad"})
    with pytest.raises(RuntimeError, match="bad"):
        fetch_fred_data("UNRATE")


@patch("fred_fetcher.requests.get")
def test_fetch_fred_no_observations_returns_empty(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(json={"observations": []})
    assert fetch_fred_data("UNRATE").is_empty()


@patch("fred_fetcher.requests.get")
def test_fetch_fred_alias_resolves_and_saves(mock_get: MagicMock, make_response, tmp_path: Path) -> None:
    mock_get.return_value = make_response(json=_OBS)
    out = tmp_path / "alias.csv"
    df = fetch_fred_alias({"my_alias": "XYZ"}, "MY_ALIAS", output_file=str(out))
    assert mock_get.call_args.kwargs["params"]["series_id"] == "XYZ"
    assert df["series"].to_list() == ["MY_ALIAS"]
    assert out.exists()
    assert pl.read_csv(out).height == 1


@patch("fred_fetcher.requests.get")
def test_fetch_fred_alias_unknown_passes_raw_id(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(json=_OBS)
    fetch_fred_alias({}, "RAWID")
    assert mock_get.call_args.kwargs["params"]["series_id"] == "RAWID"
