"""Tests for edinet_fetcher.py (edinetdb クライアントをモック)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import polars as pl
import pytest
from edinetdb.client import AuthError, RateLimitError, Response, ServerError

import edinet_fetcher
from edinet_fetcher import fetch_edinet_financials, fetch_edinet_ratios


def _resp(data: object) -> Response:
    return Response(data=data, meta={}, rate_limit={}, status_code=200)


@pytest.fixture
def no_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """edinet 側の tenacity リトライの待機を0にする（tenacity.nap.sleep の patch は効かないため）。"""
    monkeypatch.setattr(edinet_fetcher._client_get.retry, "sleep", lambda _s: None)


@patch("edinet_fetcher.edinet_client.Client")
def test_financials_returns_dataframe_and_saves(mock_client_cls: MagicMock, tmp_path: Path) -> None:
    mock_client_cls.return_value.get.return_value = _resp([
        {"fiscal_year": 2023, "revenue": 100},
        {"fiscal_year": 2024, "revenue": 120},
    ])
    out = tmp_path / "fin.csv"

    df = fetch_edinet_financials("E02144", period="annual", years=2, output_file=str(out))
    assert isinstance(df, pl.DataFrame)
    assert df.height == 2
    assert out.exists()
    path, kwargs = mock_client_cls.return_value.get.call_args
    assert path[0] == "/companies/E02144/financials"
    assert kwargs["params"] == {"period": "annual", "years": 2}


@patch("edinet_fetcher.edinet_client.Client")
def test_ratios_returns_dataframe(mock_client_cls: MagicMock) -> None:
    mock_client_cls.return_value.get.return_value = _resp([{"fiscal_year": 2024, "roe": 0.1}])

    df = fetch_edinet_ratios("E02144")
    assert df.height == 1
    assert mock_client_cls.return_value.get.call_args[0][0] == "/companies/E02144/ratios"


@pytest.mark.parametrize("fetch", [fetch_edinet_financials, fetch_edinet_ratios])
@patch("edinet_fetcher.edinet_client.Client")
def test_no_data_returns_empty_and_writes_no_csv(
    mock_client_cls: MagicMock, fetch, tmp_path: Path
) -> None:
    """0件のとき改行だけの CSV を書かない（Hub 側の NoDataError の原因）。空DFを返す。"""
    mock_client_cls.return_value.get.return_value = _resp([])
    out = tmp_path / "empty.csv"

    df = fetch("E00000", output_file=str(out))
    assert isinstance(df, pl.DataFrame)
    assert df.is_empty()
    assert not out.exists()


@patch("edinet_fetcher.edinet_client.Client")
def test_hub_no_data_is_empty_not_error(mock_client_cls: MagicMock, hub) -> None:
    """Hub 経由: 0件は例外ではなく空DF（改行だけの CSV を読んで失敗しない）。"""
    mock_client_cls.return_value.get.return_value = _resp([])

    df = hub.get_edinet_financials("E00000")
    assert df.is_empty()


def test_unknown_kwargs_raise_type_error() -> None:
    """未知の引数を黙って捨てない。"""
    with pytest.raises(TypeError):
        fetch_edinet_financials("E02144", perod="annual")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        fetch_edinet_ratios("E02144", years=3)  # type: ignore[call-arg]


@pytest.mark.parametrize("transient", [
    RateLimitError("Rate limit exceeded", limit=None, reset=None, upgrade_url=None),
    ServerError("Server error (503)"),
    httpx.ConnectError("connection refused"),
])
@patch("edinet_fetcher.edinet_client.Client")
def test_transient_errors_are_retried(
    mock_client_cls: MagicMock, transient: Exception, no_retry_wait: None
) -> None:
    """edinetdb の一時エラー（429/5xx/接続）はリトライされる。"""
    mock_client_cls.return_value.get.side_effect = [transient, _resp([{"fiscal_year": 2024}])]

    df = fetch_edinet_ratios("E02144")
    assert df.height == 1
    assert mock_client_cls.return_value.get.call_count == 2


@patch("edinet_fetcher.edinet_client.Client")
def test_auth_error_not_retried(mock_client_cls: MagicMock, no_retry_wait: None) -> None:
    """認証エラー等の恒久エラーはリトライせず即失敗。"""
    mock_client_cls.return_value.get.side_effect = AuthError("invalid key")

    with pytest.raises(AuthError):
        fetch_edinet_ratios("E02144")
    assert mock_client_cls.return_value.get.call_count == 1
