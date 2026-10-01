"""Tests for pmi_fetcher.py (FRED経由、FRED_API_KEY設定済み→実API)."""
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest
from dotenv import load_dotenv


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
def test_mock_fred_response(mock_get: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    monkeypatch.setenv("FRED_API_KEY", "test_key_mock")

    out = str(tmp_path / "pmi_mock.csv")
    df = fetch_pmi_data(series="us_new_orders", output_file=out)
    # 欠損1件除外で2件
    assert df.height == 2
    assert Path(out).exists()


@patch("fred_fetcher.requests.get")
def test_mock_http_error(mock_get: MagicMock, monkeypatch: pytest.MonkeyPatch, make_response) -> None:
    """HTTPエラーは空DataFrameに化けず送出される。"""
    import requests
    mock_get.return_value = make_response(text="err", status=400)

    monkeypatch.setenv("FRED_API_KEY", "test_key_mock")

    with pytest.raises(requests.exceptions.HTTPError):
        fetch_pmi_data(series="us_new_orders")


@patch("fred_fetcher.requests.get")
def test_pmi_alias_resolves_to_fred_id(
    mock_get: MagicMock, monkeypatch: pytest.MonkeyPatch, make_response
) -> None:
    """エイリアスは FRED 系列IDに解決され、series 列にはエイリアス名が入る。"""
    mock_get.return_value = make_response(json={"observations": [{"date": "2023-01-01", "value": "1"}]})
    monkeypatch.setenv("FRED_API_KEY", "test_key_mock")

    df = fetch_pmi_data(series="oecd_cli_jp")
    assert mock_get.call_args.kwargs["params"]["series_id"] == PMI_SERIES["oecd_cli_jp"]
    assert df["series"].to_list() == ["oecd_cli_jp"]
