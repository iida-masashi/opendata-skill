"""Tests for freight_fetcher.py (yahoo_fetcher 経由の海運プロキシ)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import polars as pl
import pytest
from freight_fetcher import (
    FREIGHT_ETF_PRESETS,
    FREIGHT_INDEX_SERIES,
    fetch_freight_data,
    fetch_freight_index,
)


def _yf_download_like(tickers: list[str]) -> pd.DataFrame:
    """yfinance 1.x の yf.download(group_by='ticker') 相当（列 MultiIndex [Ticker, Price]）。"""
    idx = pd.date_range("2024-01-01", periods=3, freq="B")
    idx.name = "Date"
    frames = [
        pd.DataFrame(
            {"Close": [10.0 + i, 11.0 + i, 12.0 + i], "High": [13.0] * 3, "Low": [9.0] * 3,
             "Open": [10.0] * 3, "Volume": [100, 200, 300]},
            index=idx,
        )
        for i in range(len(tickers))
    ]
    return pd.concat(frames, axis=1, keys=tickers, names=["Ticker", "Price"])


@patch("yahoo_fetcher.yf.download")
def test_freight_keeps_legacy_schema(mock_dl: MagicMock) -> None:
    """出力スキーマ（Date 文字列 / Ticker / Close ...）は従来どおり。"""
    mock_dl.return_value = _yf_download_like(["BDRY"])

    df = fetch_freight_data("BDRY", "2024-01-01", "2024-01-05")

    assert df.columns[:3] == ["Date", "Ticker", "Close"]
    assert {"High", "Low", "Open", "Volume"} <= set(df.columns)
    assert df.schema["Date"] == pl.String
    assert df["Date"].to_list() == ["2024-01-01", "2024-01-02", "2024-01-03"]
    assert df["Ticker"].unique().to_list() == ["BDRY"]


@pytest.mark.parametrize("tickers", ["BDRY,ZIM", "BDRY, ZIM", "BDRY ZIM"])
@patch("yahoo_fetcher.yf.download")
def test_freight_accepts_comma_and_space(mock_dl: MagicMock, tickers: str) -> None:
    """カンマ区切り（従来の freight）とスペース区切り（yahoo/Hub）の両方を受け付ける。"""
    mock_dl.return_value = _yf_download_like(["BDRY", "ZIM"])

    df = fetch_freight_data(tickers, "2024-01-01", "2024-01-05")

    assert mock_dl.call_args[0][0] == ["BDRY", "ZIM"]
    assert sorted(df["Ticker"].unique().to_list()) == ["BDRY", "ZIM"]


@patch("yahoo_fetcher.yf.download")
def test_freight_saves_csv(mock_dl: MagicMock, tmp_path: Path) -> None:
    mock_dl.return_value = _yf_download_like(["BDRY"])
    out = tmp_path / "freight.csv"

    fetch_freight_data("BDRY", "2024-01-01", "2024-01-05", output_file=str(out))

    assert pl.read_csv(out).height == 3


@patch("yahoo_fetcher.yf.download")
def test_freight_empty_raises(mock_dl: MagicMock) -> None:
    """取得0件（yfinance の失敗）は空DFでなく例外。"""
    mock_dl.return_value = pd.DataFrame()

    with pytest.raises(RuntimeError, match="No data"):
        fetch_freight_data("BDRY", "2024-01-01", "2024-01-05")


@patch("yahoo_fetcher.yf.download")
def test_freight_exception_propagates(mock_dl: MagicMock) -> None:
    mock_dl.side_effect = ConnectionError("boom")

    with pytest.raises(ConnectionError):
        fetch_freight_data("BDRY", "2024-01-01", "2024-01-05")


@patch("yahoo_fetcher.yf.download")
def test_hub_get_freight(mock_dl: MagicMock, hub) -> None:
    """Hub 経由で date/value に正規化されて返る。"""
    mock_dl.return_value = _yf_download_like(["BDRY"])

    df = hub.get_freight(tickers="BDRY", start_date="2024-01-01", end_date="2024-01-05")

    assert {"date", "value", "Ticker"} <= set(df.columns)
    assert df.height == 3


@patch("yahoo_fetcher.yf.download")
def test_freight_etf_preset_resolves(mock_dl: MagicMock) -> None:
    """FREIGHT_ETF_PRESETS のキー（tanker, jp_liners 等）がティッカー一覧に展開される。"""
    assert "jp_liners" in FREIGHT_ETF_PRESETS
    mock_dl.return_value = _yf_download_like(["9101.T", "9104.T", "9107.T"])

    df = fetch_freight_data("jp_liners", "2024-01-01", "2024-01-05")

    assert mock_dl.call_args[0][0] == ["9101.T", "9104.T", "9107.T"]
    assert sorted(df["Ticker"].unique().to_list()) == ["9101.T", "9104.T", "9107.T"]


@pytest.mark.parametrize(
    ("alias", "expected_id"),
    [
        ("deep_sea_freight_ppi", "PCU483111483111"),
        ("air_freight_ppi", "PCU481112481112"),
        ("trucking_freight_ppi", "PCU484121484121"),
        ("cass_shipments", "FRGSHPUSM649NCIS"),
        ("cass_expenditures", "FRGEXPUSM649NCIS"),
        ("tsi_freight", "TSIFRGHT"),
    ],
)
@patch("fred_fetcher.requests.get")
def test_freight_index_resolves_and_hub_works(
    mock_get: MagicMock,
    make_response,
    monkeypatch: pytest.MonkeyPatch,
    hub,
    alias: str,
    expected_id: str,
) -> None:
    """FRED 経由の公的海運・航空・トラック運賃 PPI / Cass 物流指数が取得できる。"""
    assert FREIGHT_INDEX_SERIES[alias] == expected_id
    monkeypatch.setenv("FRED_API_KEY", "test_key")
    mock_get.return_value = make_response(
        json={"observations": [{"date": "2024-01-01", "value": "215.4"}]}
    )

    df = fetch_freight_index(alias, "2024-01-01", "2024-12-31")
    assert mock_get.call_args.kwargs["params"]["series_id"] == expected_id
    assert df["series"].to_list() == [alias]

    df_hub = hub.get_freight_index(series=alias, start_date="2024-01-01", end_date="2024-12-31")
    assert {"date", "value", "series", "series_id"} <= set(df_hub.columns)
    assert df_hub.height == 1
