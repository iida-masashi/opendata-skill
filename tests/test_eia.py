"""Tests for eia_fetcher.py (EIA_API_KEY未設定想定 → モック中心)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests


from eia_fetcher import SERIES_ALIAS, fetch_eia_data


def test_series_aliases_defined() -> None:
    for key in ["crude_stocks", "natgas_storage", "wti_price", "refinery_util"]:
        assert key in SERIES_ALIAS


@patch("eia_fetcher.requests.get")
def test_mock_crude_stocks(mock_get: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """モック: EIA v2 APIの標準レスポンスをパース。"""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "response": {
            "total": 2,
            "data": [
                {"period": "2024-01-05", "value": 430.5, "series": "WCESTUS1"},
                {"period": "2024-01-12", "value": 435.2, "series": "WCESTUS1"},
            ],
        }
    }
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    monkeypatch.setenv("EIA_API_KEY", "test_key_mock")

    out = str(tmp_path / "eia.csv")
    df = fetch_eia_data(series="crude_stocks", output_file=out)
    assert df.height == 2
    # 標準化カラム
    assert "date" in df.columns
    assert "value" in df.columns
    assert Path(out).exists()


@patch("eia_fetcher.requests.get")
def test_mock_series_resolution(mock_get: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    """エイリアスがエンドポイントに解決される。"""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": {"data": []}}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    monkeypatch.setenv("EIA_API_KEY", "test_key_mock")

    fetch_eia_data(series="natgas_storage")
    called_url = mock_get.call_args[0][0]
    assert "natural-gas" in called_url


@patch("eia_fetcher.requests.get")
def test_mock_empty(mock_get: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": {"data": []}}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    monkeypatch.setenv("EIA_API_KEY", "test_key_mock")

    df = fetch_eia_data(series="crude_stocks")
    assert df.is_empty()


@patch("eia_fetcher.requests.get")
def test_mock_http_error_raises_and_redacts_key(
    mock_get: MagicMock, make_response, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HTTP エラーは空DFに化けず例外。メッセージに API キー（URL クエリ）を出さない。"""
    mock_get.return_value = make_response(
        text='{"error":"invalid api_key"}', status=403,
        url="https://api.eia.gov/v2/petroleum/stoc/wstk/data?api_key=SECRET_EIA_KEY",
    )
    monkeypatch.setenv("EIA_API_KEY", "SECRET_EIA_KEY")

    with pytest.raises(requests.exceptions.HTTPError) as exc_info:
        fetch_eia_data(series="crude_stocks")
    assert "403" in str(exc_info.value)
    assert "SECRET_EIA_KEY" not in str(exc_info.value)


@patch("eia_fetcher.requests.get")
def test_mock_error_payload_raises(mock_get: MagicMock, make_response, monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP 200 で返る {"error": ...} は 0件扱いせず例外。"""
    mock_get.return_value = make_response(json={"error": "Invalid frequency provided."})
    monkeypatch.setenv("EIA_API_KEY", "test_key_mock")

    with pytest.raises(RuntimeError, match="Invalid frequency"):
        fetch_eia_data(series="crude_stocks")
