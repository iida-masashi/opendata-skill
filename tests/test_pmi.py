"""Tests for pmi_fetcher.py (FRED経由、FRED_API_KEY設定済み→実API)."""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

# .env を opendata-skill ルートから読み込む
load_dotenv(Path(__file__).parent.parent / ".env")

from pmi_fetcher import PMI_SERIES, fetch_pmi_data


def test_pmi_series_defined() -> None:
    """主要エイリアスが定義されている。"""
    for key in ["us_new_orders", "us_inventories", "oecd_cli_us", "oecd_cli_jp"]:
        assert key in PMI_SERIES


def test_pmi_series_are_strings() -> None:
    """すべてのシリーズIDが文字列。"""
    for v in PMI_SERIES.values():
        assert isinstance(v, str)


@pytest.mark.skipif(not os.getenv("FRED_API_KEY"), reason="FRED_API_KEY not set")
@pytest.mark.integration
def test_real_fred_us_new_orders(tmp_path: Path) -> None:
    """実API: 米製造業新規受注を取得。"""
    out = str(tmp_path / "pmi_real.csv")
    df = fetch_pmi_data(
        series="us_new_orders",
        start_date="2023-01-01",
        end_date="2023-12-31",
        output_file=out,
    )
    assert isinstance(df, pl.DataFrame)
    if not df.is_empty():
        assert "date" in df.columns
        assert "value" in df.columns
        assert df.height > 0
        assert Path(out).exists()


@pytest.mark.skipif(not os.getenv("FRED_API_KEY"), reason="FRED_API_KEY not set")
@pytest.mark.integration
def test_real_fred_oecd_cli_jp() -> None:
    """実API: 日本OECD CLIを取得。"""
    df = fetch_pmi_data(
        series="oecd_cli_jp",
        start_date="2022-01-01",
        end_date="2023-12-31",
    )
    assert isinstance(df, pl.DataFrame)


@patch("fred_fetcher.requests.get")
def test_mock_fred_response(mock_get: MagicMock, tmp_path: Path) -> None:
    """モック: FRED JSON observationsをパース。"""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "observations": [
            {"date": "2023-01-01", "value": "100.2"},
            {"date": "2023-02-01", "value": "101.5"},
            {"date": "2023-03-01", "value": "."},  # 欠損
        ]
    }
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    # FRED_API_KEY が無い場合でも、require_api_key がモックされないため環境依存
    if not os.getenv("FRED_API_KEY"):
        os.environ["FRED_API_KEY"] = "test_key_mock"

    out = str(tmp_path / "pmi_mock.csv")
    df = fetch_pmi_data(series="us_new_orders", output_file=out)
    # 欠損1件除外で2件
    assert df.height == 2
    assert Path(out).exists()


@patch("fred_fetcher.requests.get")
def test_mock_http_error(mock_get: MagicMock) -> None:
    """HTTPエラーで空DataFrame。"""
    import requests
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=MagicMock(text="err"))
    mock_get.return_value = mock_resp

    if not os.getenv("FRED_API_KEY"):
        os.environ["FRED_API_KEY"] = "test_key_mock"

    df = fetch_pmi_data(series="us_new_orders")
    assert df.is_empty()
