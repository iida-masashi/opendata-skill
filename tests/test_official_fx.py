"""Tests for official_fx_fetcher.py (ECB/BOJ - APIキー不要、実API)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest
import requests
from official_fx_fetcher import fetch_boj_fx, fetch_ecb_fx, fetch_official_fx

ECB_CSV = (
    "KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE,OBS_STATUS\n"
    "EXR.D.JPY.EUR.SP00.A,D,JPY,EUR,SP00,A,2024-01-02,158.32,A\n"
    "EXR.D.JPY.EUR.SP00.A,D,JPY,EUR,SP00,A,2024-01-03,158.45,A\n"
)
FRANKFURTER_JSON = {
    "rates": {
        "2024-01-02": {"JPY": 144.5},
        "2024-01-03": {"JPY": 145.2},
    }
}


@pytest.mark.integration
def test_real_ecb_jpy() -> None:
    """実API: ECB EUR/JPY 日次レート取得。"""
    df = fetch_ecb_fx(currency="JPY", start_date="2024-01-01", end_date="2024-01-31")
    assert df.height > 0
    assert "value" in df.columns


@pytest.mark.integration
def test_real_boj_usd() -> None:
    """実API: Frankfurter経由のUSD/JPY取得。"""
    df = fetch_boj_fx(currency="USD", start_date="2024-01-01", end_date="2024-01-15")
    assert df.height > 0
    assert {"value", "pair"} <= set(df.columns)


@pytest.mark.integration
def test_real_official_fx_ecb(tmp_path: Path) -> None:
    """実API: 統合IF経由でECBレートを保存できる。"""
    out = tmp_path / "fx_real.csv"
    df = fetch_official_fx(
        source="ecb", currency="USD",
        start_date="2024-01-01", end_date="2024-01-10",
        output_file=str(out),
    )
    assert df.height > 0
    assert out.exists()


@patch("official_fx_fetcher.requests.get")
def test_mock_ecb_csv_parse(mock_get: MagicMock, make_response) -> None:
    """モック: ECB CSVレスポンスをパース。"""
    mock_get.return_value = make_response(text=ECB_CSV)

    df = fetch_ecb_fx(currency="JPY", start_date="2024-01-01", end_date="2024-01-31")
    assert df.height == 2
    assert "value" in df.columns


@patch("official_fx_fetcher.requests.get")
def test_mock_ecb_empty_body_is_empty_df(mock_get: MagicMock, make_response) -> None:
    """正常応答で本文が空 = 0件。空DFを返す。"""
    mock_get.return_value = make_response(text="")

    df = fetch_ecb_fx(currency="JPY", start_date="2024-01-01", end_date="2024-01-31")
    assert df.is_empty()


@patch("official_fx_fetcher.requests.get")
def test_mock_ecb_unparsable_body_raises(mock_get: MagicMock, make_response) -> None:
    """CSV として壊れた応答は空DFに縮退させず例外。"""
    mock_get.return_value = make_response(text='a,b\n1,2,3,4\n"unterminated')

    with pytest.raises(Exception):  # noqa: B017
        fetch_ecb_fx(currency="JPY", start_date="2024-01-01", end_date="2024-01-31")


@patch("official_fx_fetcher.requests.get")
def test_mock_boj_frankfurter(mock_get: MagicMock, make_response) -> None:
    """モック: Frankfurter JSON レスポンス。"""
    mock_get.return_value = make_response(json=FRANKFURTER_JSON)

    df = fetch_boj_fx(currency="USD", start_date="2024-01-01", end_date="2024-01-10")
    assert df.height == 2
    assert df.get_column("value").to_list() == [144.5, 145.2]


def test_boj_unknown_currency_raises() -> None:
    """未対応通貨でValueError。"""
    with pytest.raises(ValueError, match="JPY FX not supported"):
        fetch_boj_fx(currency="XYZ")


@patch("official_fx_fetcher.requests.get")
def test_official_fx_boj_with_default_currency(mock_get: MagicMock, make_response) -> None:
    """source='boj' に既定の currency='JPY'（Hub も明示的に渡す）でも ValueError にならず USD/JPY を返す。"""
    mock_get.return_value = make_response(json=FRANKFURTER_JSON)

    df = fetch_official_fx(source="boj", currency="JPY", start_date="2024-01-01", end_date="2024-01-10")

    assert df.height == 2
    assert df["pair"].unique().to_list() == ["USD/JPY"]
    assert mock_get.call_args[1]["params"]["from"] == "USD"


@patch("official_fx_fetcher.requests.get")
def test_hub_get_official_fx_boj(mock_get: MagicMock, make_response, hub) -> None:
    """Hub の get_official_fx(source='boj') が空DFでなくデータを返す。"""
    mock_get.return_value = make_response(json=FRANKFURTER_JSON)

    df = hub.get_official_fx(source="boj", start_date="2024-01-01", end_date="2024-01-10")

    assert df.height == 2
    assert {"date", "value"} <= set(df.columns)


@patch("official_fx_fetcher.requests.get")
def test_http_error_raises(mock_get: MagicMock, make_response) -> None:
    """HTTP 4xx は空DFでなく HTTPError を送出する。"""
    mock_get.return_value = make_response(status=404, text="No results found")

    with pytest.raises(requests.exceptions.HTTPError):
        fetch_official_fx(source="ecb", currency="USD")


@patch("api_utils.get_with_retry.retry.sleep")
@patch("official_fx_fetcher.requests.get")
def test_5xx_is_retried(mock_get: MagicMock, _sleep: MagicMock, make_response) -> None:
    """5xx はリトライされ、回復すればデータを返す。"""
    mock_get.side_effect = [make_response(status=503), make_response(json=FRANKFURTER_JSON)]

    df = fetch_official_fx(source="boj", currency="USD", start_date="2024-01-01", end_date="2024-01-10")

    assert df.height == 2
    assert mock_get.call_count == 2


@patch("official_fx_fetcher.requests.get")
def test_frankfurter_error_payload_raises(mock_get: MagicMock, make_response) -> None:
    """rates を持たないエラーペイロードは空DFにせず例外。"""
    mock_get.return_value = make_response(json={"message": "not found"})

    with pytest.raises(RuntimeError, match="not found"):
        fetch_boj_fx(currency="USD", start_date="2024-01-01", end_date="2024-01-10")


def test_unknown_source_raises() -> None:
    with pytest.raises(ValueError, match="Unknown source"):
        fetch_official_fx(source="xxx")


@patch("official_fx_fetcher.requests.get")
def test_official_fx_saves_csv(mock_get: MagicMock, make_response, tmp_path: Path) -> None:
    mock_get.return_value = make_response(text=ECB_CSV)
    out = tmp_path / "fx.csv"

    fetch_official_fx(source="ecb", currency="JPY", output_file=str(out))

    assert isinstance(pl.read_csv(out), pl.DataFrame)
