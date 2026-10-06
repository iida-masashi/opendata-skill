"""Tests for yahoo_fetcher.py (Yahoo Finance via yfinance)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import polars as pl
import pytest
from yahoo_fetcher import fetch_yahoo_finance


def _one_ticker_frame(intraday: bool, base: float) -> pd.DataFrame:
    """yfinance の1ティッカー分の履歴（日次は tz-naive の Date、日中足は tz-aware の Datetime）。"""
    if intraday:
        idx = pd.date_range("2024-01-04 09:00", periods=3, freq="h", tz="Asia/Tokyo")
        idx.name = "Datetime"
    else:
        idx = pd.date_range("2024-01-01", periods=3, freq="B")
        idx.name = "Date"
    return pd.DataFrame(
        {
            "Close": [base, base + 1, base + 2],
            "High": [base + 3] * 3,
            "Low": [base - 3] * 3,
            "Open": [base] * 3,
            "Volume": [1000, 1200, 900],
        },
        index=idx,
    )


def _yf_download_like(tickers: list[str], intraday: bool = False) -> pd.DataFrame:
    """yfinance 1.x の yf.download(group_by='ticker') と同じ形（列は MultiIndex [Ticker, Price]）。

    multi_level_index=True が既定なので、単一ティッカーでも MultiIndex になる。
    """
    frames = [_one_ticker_frame(intraday, 100.0 * (i + 1)) for i in range(len(tickers))]
    return pd.concat(frames, axis=1, keys=tickers, names=["Ticker", "Price"])


def _mock_single_ticker_flat_df() -> pd.DataFrame:
    """単一ティッカーの flat DataFrame（multi_level_index=False 相当）。"""
    return _one_ticker_frame(intraday=False, base=150.0)


@patch("yahoo_fetcher.yf.download")
def test_fetch_single_ticker_saves_csv(mock_dl: MagicMock, tmp_path: Path) -> None:
    """正常系: 単一ティッカーのデータをCSVに保存する。"""
    mock_dl.return_value = _yf_download_like(["7203.T"])

    out = str(tmp_path / "yahoo_test.csv")
    result = fetch_yahoo_finance("7203.T", "2024-01-01", "2024-01-05", output_file=out)

    assert Path(out).exists()
    assert isinstance(result, pl.DataFrame)


@patch("yahoo_fetcher.yf.download")
def test_fetch_single_ticker_flat_columns(mock_dl: MagicMock) -> None:
    """flat 列（MultiIndex でない）でも date/value/Ticker を返す。"""
    mock_dl.return_value = _mock_single_ticker_flat_df()

    df = fetch_yahoo_finance("7203.T", "2024-01-01", "2024-01-05")

    assert {"date", "value", "Ticker"} <= set(df.columns)
    assert df["Ticker"].unique().to_list() == ["7203.T"]
    assert df["value"].to_list() == [150.0, 151.0, 152.0]


@patch("yahoo_fetcher.yf.download")
def test_daily_single_ticker_multiindex_has_date(mock_dl: MagicMock) -> None:
    """yfinance 1.x の単一ティッカー（MultiIndex 列）で date 列が日時型で残る。"""
    mock_dl.return_value = _yf_download_like(["7203.T"])

    df = fetch_yahoo_finance("7203.T", "2024-01-01", "2024-01-05")

    assert df.columns[0] == "date"
    assert df.schema["date"] == pl.Datetime("us")
    assert df.height == 3
    assert df["value"].to_list() == [100.0, 101.0, 102.0]
    assert df["Ticker"].unique().to_list() == ["7203.T"]


@patch("yahoo_fetcher.yf.download")
def test_intraday_single_ticker_has_date(mock_dl: MagicMock) -> None:
    """日中足（インデックス名 Datetime・tz付き）でも date 列が出る（以前は rename 失敗で None）。"""
    mock_dl.return_value = _yf_download_like(["7203.T"], intraday=True)

    df = fetch_yahoo_finance("7203.T", "2024-01-04", "2024-01-05", interval="1h")

    assert "date" in df.columns
    assert "Datetime" not in df.columns
    assert df.schema["date"] == pl.Datetime("us", "Asia/Tokyo")
    assert df["date"][0].hour == 9
    assert df.height == 3


@patch("yahoo_fetcher.yf.download")
def test_intraday_multi_ticker_has_date(mock_dl: MagicMock) -> None:
    """日中足 × 複数ティッカーでも date 列と各ティッカーの行が出る。"""
    mock_dl.return_value = _yf_download_like(["7203.T", "USDJPY=X"], intraday=True)

    df = fetch_yahoo_finance("7203.T USDJPY=X", "2024-01-04", "2024-01-05", interval="1h")

    assert "date" in df.columns
    assert "Datetime" not in df.columns
    assert sorted(df["Ticker"].unique().to_list()) == ["7203.T", "USDJPY=X"]
    assert df.height == 6
    assert df.filter(pl.col("Ticker") == "USDJPY=X")["value"].to_list() == [200.0, 201.0, 202.0]


@patch("yahoo_fetcher.yf.download")
def test_daily_multi_ticker_has_date_and_value(mock_dl: MagicMock) -> None:
    """日次 × 複数ティッカーで date/value/Ticker が揃う。"""
    mock_dl.return_value = _yf_download_like(["CL=F", "GC=F"])

    df = fetch_yahoo_finance("CL=F GC=F", "2024-01-01", "2024-01-05")

    assert {"date", "value", "Ticker", "High", "Low", "Open", "Volume"} <= set(df.columns)
    assert df.height == 6


@patch("yahoo_fetcher.yf.download")
def test_multi_ticker_drops_rows_missing_for_that_ticker(mock_dl: MagicMock) -> None:
    """取引カレンダーが違うティッカーの空行（全列 NaN）は落とす。"""
    # 欠損があると yfinance の concat で Volume も float になる
    raw = _yf_download_like(["A", "B"]).astype(float)
    raw.loc[raw.index[1], "B"] = float("nan")
    mock_dl.return_value = raw

    df = fetch_yahoo_finance("A B", "2024-01-01", "2024-01-05")

    assert df.filter(pl.col("Ticker") == "B").height == 2
    assert df.filter(pl.col("Ticker") == "A").height == 3


@patch("yahoo_fetcher.yf.download")
def test_comma_separated_tickers_accepted(mock_dl: MagicMock) -> None:
    """カンマ区切りもスペース区切りと同じティッカーリストとして渡す。"""
    mock_dl.return_value = _yf_download_like(["BDRY", "ZIM"])

    fetch_yahoo_finance("BDRY, ZIM", "2024-01-01", "2024-01-05")

    assert mock_dl.call_args[0][0] == ["BDRY", "ZIM"]


@patch("yahoo_fetcher.yf.download")
def test_fetch_empty_data_raises(mock_dl: MagicMock, tmp_path: Path) -> None:
    """yfinance は取得失敗を空DFにして返すため、空は失敗として例外にする。"""
    mock_dl.return_value = pd.DataFrame()

    out = tmp_path / "out.csv"
    with pytest.raises(RuntimeError, match="No data"):
        fetch_yahoo_finance("INVALID", "2024-01-01", "2024-01-05", output_file=str(out))
    assert not out.exists()


@patch("yahoo_fetcher.yf.download")
def test_fetch_default_dates_used(mock_dl: MagicMock) -> None:
    """start/end日付を省略すると自動設定されてdownloadが呼ばれる。"""
    mock_dl.return_value = _yf_download_like(["7203.T"])

    fetch_yahoo_finance("7203.T")

    call_kwargs = mock_dl.call_args[1]
    assert call_kwargs["start"]
    assert call_kwargs["end"]


@patch("yahoo_fetcher.yf.download")
def test_fetch_exception_propagates(mock_dl: MagicMock) -> None:
    """yfinance の例外は握り潰さず送出する。"""
    mock_dl.side_effect = Exception("yfinance error")

    with pytest.raises(Exception, match="yfinance error"):
        fetch_yahoo_finance("7203.T", "2024-01-01", "2024-01-05")


@patch("yahoo_fetcher.yf.download")
def test_no_output_file_writes_nothing(
    mock_dl: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """output_file=None ではファイルを書かない（Hub/ライブラリ利用でCWDを汚さない）。"""
    mock_dl.return_value = _yf_download_like(["7203.T"])
    monkeypatch.chdir(tmp_path)

    fetch_yahoo_finance("7203.T", "2024-01-01", "2024-01-05")

    assert list(tmp_path.iterdir()) == []


@patch("yahoo_fetcher.yf.download")
def test_lith_missing_falls_back_to_lit(mock_dl: MagicMock) -> None:
    """LITH=F が全欠損なら LIT で補う。"""
    lith = _yf_download_like(["LITH=F", "CL=F"]).astype(float)
    lith.loc[:, "LITH=F"] = float("nan")
    lit = _yf_download_like(["LIT"])
    mock_dl.side_effect = [lith, lit]

    df = fetch_yahoo_finance("LITH=F CL=F", "2024-01-01", "2024-01-05")

    assert sorted(df["Ticker"].unique().to_list()) == ["CL=F", "LIT"]
    assert mock_dl.call_args_list[1][0][0] == ["LIT"]


@patch("yahoo_fetcher.yf.download")
def test_lith_present_does_not_fetch_lit(mock_dl: MagicMock) -> None:
    """LITH=F が取れていれば LIT を追加取得しない。"""
    mock_dl.return_value = _yf_download_like(["LITH=F"])

    df = fetch_yahoo_finance("LITH=F", "2024-01-01", "2024-01-05")

    assert mock_dl.call_count == 1
    assert df["Ticker"].unique().to_list() == ["LITH=F"]


@patch("yahoo_fetcher.yf.download")
def test_hub_get_yahoo_intraday(mock_dl: MagicMock, hub) -> None:
    """Hub 経由（output_file 付き）でも日中足が date/value で返る。"""
    mock_dl.return_value = _yf_download_like(["7203.T", "USDJPY=X"], intraday=True)

    df = hub.get_yahoo(symbol="7203.T USDJPY=X", start_date="2024-01-04", end_date="2024-01-05", interval="1h")

    assert {"date", "value", "Ticker"} <= set(df.columns)
    assert df.height == 6


@pytest.mark.parametrize("intraday", [False, True])
@patch("yahoo_fetcher.yf.download")
def test_second_resolution_index_converts(mock_dl: MagicMock, intraday: bool) -> None:
    """pandas 3 の yfinance は日付を秒精度（datetime64[s]）で返すことがある。
    Polars は numpy の秒精度を受け付けないため、マイクロ秒にそろえて変換する。"""
    pdf = _one_ticker_frame(intraday, 100.0)
    unit = "datetime64[s, Asia/Tokyo]" if intraday else "datetime64[s]"
    pdf.index = pdf.index.astype(unit)
    mock_dl.return_value = pd.concat([pdf], axis=1, keys=["7203.T"], names=["Ticker", "Price"])

    df = fetch_yahoo_finance("7203.T", "2024-01-01", "2024-01-05")

    expected = pl.Datetime("us", "Asia/Tokyo") if intraday else pl.Datetime("us")
    assert df.schema["date"] == expected
    assert df["date"][0].hour == (9 if intraday else 0)
    assert df["value"].to_list() == [100.0, 101.0, 102.0]
