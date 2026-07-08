"""Tests for eia_fetcher.py (EIA_API_KEY未設定想定 → モック中心)."""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from eia_fetcher import SERIES_ALIAS, fetch_eia_data


def test_series_aliases_defined() -> None:
    for key in ["crude_stocks", "natgas_storage", "wti_price", "refinery_util"]:
        assert key in SERIES_ALIAS


@patch("eia_fetcher.requests.get")
def test_mock_crude_stocks(mock_get: MagicMock, tmp_path: Path) -> None:
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

    if not os.getenv("EIA_API_KEY"):
        os.environ["EIA_API_KEY"] = "test_key_mock"

    out = str(tmp_path / "eia.csv")
    df = fetch_eia_data(series="crude_stocks", output_file=out)
    assert df.height == 2
    # 標準化カラム
    assert "date" in df.columns
    assert "value" in df.columns
    assert Path(out).exists()


@patch("eia_fetcher.requests.get")
def test_mock_series_resolution(mock_get: MagicMock) -> None:
    """エイリアスがエンドポイントに解決される。"""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": {"data": []}}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    if not os.getenv("EIA_API_KEY"):
        os.environ["EIA_API_KEY"] = "test_key_mock"

    fetch_eia_data(series="natgas_storage")
    called_url = mock_get.call_args[0][0]
    assert "natural-gas" in called_url


@patch("eia_fetcher.requests.get")
def test_mock_empty(mock_get: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": {"data": []}}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    if not os.getenv("EIA_API_KEY"):
        os.environ["EIA_API_KEY"] = "test_key_mock"

    df = fetch_eia_data(series="crude_stocks")
    assert df.is_empty()


@patch("eia_fetcher.requests.get")
def test_mock_http_error(mock_get: MagicMock) -> None:
    import requests
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=MagicMock(text="403"))
    mock_get.return_value = mock_resp

    if not os.getenv("EIA_API_KEY"):
        os.environ["EIA_API_KEY"] = "test_key_mock"

    df = fetch_eia_data(series="crude_stocks")
    assert df.is_empty()
