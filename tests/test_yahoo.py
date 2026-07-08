"""Tests for yahoo_fetcher.py (Yahoo Finance via yfinance)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from yahoo_fetcher import fetch_yahoo_finance


def _mock_single_ticker_df() -> pd.DataFrame:
    """単一ティッカーのflat DataFrameを生成する。"""
    dates = pd.date_range("2024-01-01", periods=3, freq="B")
    df = pd.DataFrame(
        {"Close": [150.0, 152.0, 148.0], "Volume": [1000, 1200, 900]},
        index=dates,
    )
    df.index.name = "Date"
    return df


@patch("yahoo_fetcher.yf.download")
def test_fetch_single_ticker_saves_csv(mock_dl: MagicMock, tmp_path: Path) -> None:
    """正常系: 単一ティッカーのデータをCSVに保存する。"""
    mock_dl.return_value = _mock_single_ticker_df()

    out = str(tmp_path / "yahoo_test.csv")
    result = fetch_yahoo_finance("7203.T", "2024-01-01", "2024-01-05", output_file=out)

    assert Path(out).exists()
    assert result is not None


@patch("yahoo_fetcher.yf.download")
def test_fetch_returns_polars_dataframe(mock_dl: MagicMock, tmp_path: Path) -> None:
    """戻り値がPolars DataFrameであること。"""
    import polars as pl
    mock_dl.return_value = _mock_single_ticker_df()

    result = fetch_yahoo_finance(
        "7203.T", "2024-01-01", "2024-01-05",
        output_file=str(tmp_path / "out.csv")
    )

    assert isinstance(result, pl.DataFrame)


@patch("yahoo_fetcher.yf.download")
def test_fetch_empty_data_returns_none(mock_dl: MagicMock, tmp_path: Path) -> None:
    """データが空のときNoneを返す。"""
    mock_dl.return_value = pd.DataFrame()

    result = fetch_yahoo_finance(
        "INVALID", "2024-01-01", "2024-01-05",
        output_file=str(tmp_path / "out.csv")
    )

    assert result is None


@patch("yahoo_fetcher.yf.download")
def test_fetch_default_dates_used(mock_dl: MagicMock, tmp_path: Path) -> None:
    """start/end日付を省略すると自動設定されてdownloadが呼ばれる。"""
    mock_dl.return_value = _mock_single_ticker_df()

    fetch_yahoo_finance("7203.T", output_file=str(tmp_path / "out.csv"))

    assert mock_dl.called
    call_kwargs = mock_dl.call_args[1]
    assert "start" in call_kwargs
    assert "end" in call_kwargs


@patch("yahoo_fetcher.yf.download")
def test_fetch_exception_returns_none(mock_dl: MagicMock, tmp_path: Path) -> None:
    """yfinance例外時にNoneを返す（クラッシュしない）。"""
    mock_dl.side_effect = Exception("yfinance error")

    result = fetch_yahoo_finance(
        "7203.T", "2024-01-01", "2024-01-05",
        output_file=str(tmp_path / "out.csv")
    )

    assert result is None
