"""Tests for official_fx_fetcher.py (ECB/BOJ - APIキー不要、実API)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from official_fx_fetcher import fetch_boj_fx, fetch_ecb_fx, fetch_official_fx


@pytest.mark.integration
def test_real_ecb_jpy() -> None:
    """実API: ECB EUR/JPY 日次レート取得。"""
    df = fetch_ecb_fx(currency="JPY", start_date="2024-01-01", end_date="2024-01-31")
    assert isinstance(df, pl.DataFrame)
    if not df.is_empty():
        assert "value" in df.columns or "OBS_VALUE" in df.columns


@pytest.mark.integration
def test_real_boj_usd() -> None:
    """実API: Frankfurter経由のUSD/JPY取得。"""
    df = fetch_boj_fx(currency="USD", start_date="2024-01-01", end_date="2024-01-15")
    assert isinstance(df, pl.DataFrame)
    if not df.is_empty():
        assert "value" in df.columns
        assert "pair" in df.columns


@pytest.mark.integration
def test_real_official_fx_ecb(tmp_path: Path) -> None:
    """実API: 統合IF経由でECBレートを保存できる。"""
    out = str(tmp_path / "fx_real.csv")
    df = fetch_official_fx(
        source="ecb", currency="USD",
        start_date="2024-01-01", end_date="2024-01-10",
        output_file=out,
    )
    assert isinstance(df, pl.DataFrame)


@patch("official_fx_fetcher.requests.get")
def test_mock_ecb_csv_parse(mock_get: MagicMock) -> None:
    """モック: ECB CSVレスポンスをパース。"""
    csv_body = (
        "KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE,OBS_STATUS\n"
        "EXR.D.JPY.EUR.SP00.A,D,JPY,EUR,SP00,A,2024-01-02,158.32,A\n"
        "EXR.D.JPY.EUR.SP00.A,D,JPY,EUR,SP00,A,2024-01-03,158.45,A\n"
    )
    mock_resp = MagicMock()
    mock_resp.text = csv_body
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    df = fetch_ecb_fx(currency="JPY", start_date="2024-01-01", end_date="2024-01-31")
    assert df.height == 2
    assert "value" in df.columns


@patch("official_fx_fetcher.requests.get")
def test_mock_boj_frankfurter(mock_get: MagicMock) -> None:
    """モック: Frankfurter JSON レスポンス。"""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "rates": {
            "2024-01-02": {"JPY": 144.5},
            "2024-01-03": {"JPY": 145.2},
        }
    }
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    df = fetch_boj_fx(currency="USD", start_date="2024-01-01", end_date="2024-01-10")
    assert df.height == 2
    assert df.get_column("value").to_list() == [144.5, 145.2]


def test_boj_unknown_currency_raises() -> None:
    """未対応通貨でValueError。"""
    with pytest.raises(ValueError, match="JPY FX not supported"):
        fetch_boj_fx(currency="XYZ")


@patch("official_fx_fetcher.requests.get")
def test_http_error_returns_empty(mock_get: MagicMock) -> None:
    """HTTPエラーで空DataFrame。"""
    import requests
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=MagicMock(text="err"))
    mock_get.return_value = mock_resp

    df = fetch_official_fx(source="ecb", currency="USD")
    assert df.is_empty()
