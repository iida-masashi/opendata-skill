"""Tests for gdelt_fetcher.py (GDELT 2.0 - APIキー不要、実API)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from gdelt_fetcher import SCM_RISK_THEMES, fetch_gdelt_data


def test_scm_risk_themes_defined() -> None:
    """SCMリスクテーマエイリアスが定義されている。"""
    for key in ["supply_chain", "port_congestion", "strike", "sanctions"]:
        assert key in SCM_RISK_THEMES


def test_scm_risk_themes_uppercase() -> None:
    """テーマコードは大文字。"""
    for val in SCM_RISK_THEMES.values():
        assert val.isupper() or "_" in val


@pytest.mark.integration
def test_fetch_real_api_timeline(tmp_path: Path) -> None:
    """実API: timelinevolinfo モードで時系列ボリュームが取得できる。"""
    out = str(tmp_path / "gdelt_real.csv")
    df = fetch_gdelt_data(
        query="supply chain",
        mode="timelinevolinfo",
        max_records=50,
        output_file=out,
    )
    # 空でもクラッシュしないこと、DataFrameが返ること
    assert isinstance(df, pl.DataFrame)


@patch("gdelt_fetcher.requests.get")
def test_fetch_mock_timeline(mock_get: MagicMock, tmp_path: Path) -> None:
    """モック: timelinevolinfo JSON レスポンスをパースできる。"""
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "application/json"}
    mock_resp.json.return_value = {
        "timeline": [
            {"data": [
                {"date": "20260101T000000Z", "value": 123, "norm": 0.5},
                {"date": "20260102T000000Z", "value": 456, "norm": 0.8},
            ]}
        ]
    }
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    out = str(tmp_path / "gdelt_mock.csv")
    df = fetch_gdelt_data(query="test", mode="timelinevolinfo", output_file=out)
    assert df.height == 2
    assert Path(out).exists()


@patch("gdelt_fetcher.requests.get")
def test_fetch_mock_artlist(mock_get: MagicMock) -> None:
    """モック: artlist モードで記事一覧を取得できる。"""
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "application/json"}
    mock_resp.json.return_value = {
        "articles": [
            {"url": "https://example.com/1", "title": "port closure", "seendate": "20260101T00Z"},
        ]
    }
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    df = fetch_gdelt_data(query="port", mode="artlist")
    assert df.height == 1


@patch("gdelt_fetcher.requests.get")
def test_fetch_with_theme_filter(mock_get: MagicMock) -> None:
    """テーマエイリアスがクエリに反映される。"""
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "application/json"}
    mock_resp.json.return_value = {"timeline": [{"data": []}]}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    fetch_gdelt_data(query="shipping", theme="port_congestion")
    called_params = mock_get.call_args[1]["params"]
    assert "PORT" in called_params["query"]


@patch("gdelt_fetcher.requests.get")
def test_fetch_http_error_no_crash(mock_get: MagicMock) -> None:
    """HTTPエラー時にクラッシュせず空DataFrameを返す。"""
    import requests
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=MagicMock(text="err"))
    mock_get.return_value = mock_resp

    df = fetch_gdelt_data(query="x")
    assert df.is_empty()
