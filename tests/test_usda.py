"""Tests for usda_fetcher.py (FAOSTAT: 実API, USDA: モック)."""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from usda_fetcher import (
    FAOSTAT_DOMAIN,
    USDA_COMMODITY_ALIAS,
    fetch_agri_data,
    fetch_faostat,
    fetch_usda_quickstats,
)


def test_aliases_defined() -> None:
    for key in ["corn", "wheat", "soybean", "rice"]:
        assert key in USDA_COMMODITY_ALIAS
    for key in ["production", "trade", "prices"]:
        assert key in FAOSTAT_DOMAIN


@pytest.mark.integration
def test_real_faostat_small_query() -> None:
    """実API: FAOSTATから小規模なクエリ実行 (キー不要)。
    FAOSTAT は Cloudflare 経由で稀に 521/502 を返すため例外許容。"""
    import requests
    try:
        df = fetch_faostat(
            domain="production",
            area="JPN",
            item="15",
            year="2022",
        )
        assert isinstance(df, pl.DataFrame)
    except requests.exceptions.HTTPError as e:
        # FAOSTATのCloudflareが一時的に521返却することがある → API側問題としてskip扱い
        pytest.skip(f"FAOSTAT transient error: {e}")


@patch("usda_fetcher.requests.get")
def test_mock_faostat_response(mock_get: MagicMock) -> None:
    """モック: FAOSTAT JSONレスポンスをパース。"""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": [
            {"Area": "Japan", "Item": "Wheat", "Year": 2022, "Value": 1000.5, "Unit": "t"},
            {"Area": "Japan", "Item": "Wheat", "Year": 2023, "Value": 1100.2, "Unit": "t"},
        ]
    }
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    df = fetch_faostat(domain="production", area="JPN", item="15", year="2022,2023")
    assert df.height == 2


@patch("usda_fetcher.requests.get")
def test_mock_usda_quickstats(mock_get: MagicMock) -> None:
    """モック: USDA QuickStatsレスポンス (USDA_API_KEY未設定時はモック利用)。"""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": [
            {"commodity_desc": "CORN", "year": "2023", "state_name": "US TOTAL", "Value": "15000000"},
        ]
    }
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    if not os.getenv("USDA_API_KEY"):
        os.environ["USDA_API_KEY"] = "test_key_mock"

    df = fetch_usda_quickstats(commodity="corn", year="2023")
    assert df.height == 1


@patch("usda_fetcher.requests.get")
def test_fetch_agri_integration_faostat(mock_get: MagicMock, tmp_path: Path) -> None:
    """統合IF: FAOSTAT経由で CSV 保存。"""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": [{"Area": "Japan", "Value": 500}]}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    out = str(tmp_path / "agri.csv")
    df = fetch_agri_data(
        source="faostat",
        commodity="corn",
        year="2022",
        output_file=out,
    )
    assert df.height == 1
    assert Path(out).exists()


@patch("usda_fetcher.requests.get")
def test_fetch_agri_empty(mock_get: MagicMock) -> None:
    """空データでクラッシュしない。"""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": []}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    df = fetch_agri_data(source="faostat", commodity="corn")
    assert df.is_empty()
