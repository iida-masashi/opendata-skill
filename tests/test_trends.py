"""Tests for trends_fetcher.py (Google Trends via pytrends)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import polars as pl
import pytest
from trends_fetcher import fetch_google_trends


def _mock_trends_df(last_partial: bool = False) -> pd.DataFrame:
    """pytrends.interest_over_time()が返すようなDataFrameを生成する。"""
    dates = pd.date_range("2024-01-01", periods=4, freq="W")
    df = pd.DataFrame(
        {
            "Python": [80, 85, 78, 90],
            "Rust": [30, 35, 32, 40],
            "isPartial": [False, False, False, last_partial],
        },
        index=dates,
    )
    df.index.name = "date"
    return df


def _mock_trendreq(mock_trendreq: MagicMock, df: pd.DataFrame) -> MagicMock:
    mock_instance = MagicMock()
    mock_instance.interest_over_time.return_value = df
    mock_trendreq.return_value = mock_instance
    return mock_instance


@patch("trends_fetcher.TrendReq")
def test_fetch_trends_saves_csv(mock_trendreq: MagicMock, tmp_path: Path) -> None:
    """正常系: Google TrendsデータをCSVに保存する。"""
    _mock_trendreq(mock_trendreq, _mock_trends_df())

    out = str(tmp_path / "trends_test.csv")
    fetch_google_trends("Python,Rust", output_file=out)

    content = Path(out).read_text()
    assert "Python" in content
    assert "Rust" in content


@patch("trends_fetcher.TrendReq")
def test_fetch_trends_returns_dataframe(mock_trendreq: MagicMock) -> None:
    """戻り値は date 列付きの Polars DataFrame。"""
    _mock_trendreq(mock_trendreq, _mock_trends_df())

    df = fetch_google_trends(["Python", "Rust"])

    assert isinstance(df, pl.DataFrame)
    assert df.columns == ["date", "Python", "Rust"]
    assert df.height == 4


@patch("trends_fetcher.TrendReq")
def test_fetch_trends_removes_ispartial(mock_trendreq: MagicMock, tmp_path: Path) -> None:
    """isPartial列が出力CSVに含まれない。"""
    _mock_trendreq(mock_trendreq, _mock_trends_df())

    out = str(tmp_path / "trends_partial.csv")
    fetch_google_trends(["Python"], output_file=out)

    content = Path(out).read_text()
    assert "isPartial" not in content


@patch("trends_fetcher.TrendReq")
def test_fetch_trends_drops_partial_period_rows(mock_trendreq: MagicMock) -> None:
    """isPartial=True（集計途中の最新期間）の行は値として残さず落とす。"""
    _mock_trendreq(mock_trendreq, _mock_trends_df(last_partial=True))

    df = fetch_google_trends(["Python", "Rust"])

    assert df.height == 3
    assert 90 not in df["Python"].to_list()


@patch("trends_fetcher.TrendReq")
def test_fetch_trends_string_keywords_split(mock_trendreq: MagicMock) -> None:
    """カンマ区切り文字列をリストに分割してbuild_payloadに渡す。"""
    mock_instance = _mock_trendreq(mock_trendreq, _mock_trends_df())

    fetch_google_trends("Python,Rust")

    call_args = mock_instance.build_payload.call_args[0]
    assert call_args[0] == ["Python", "Rust"]


@pytest.mark.parametrize("geo", ["world", "WORLD", ""])
@patch("trends_fetcher.TrendReq")
def test_world_geo_maps_to_empty(mock_trendreq: MagicMock, geo: str) -> None:
    """pytrends の全世界指定は geo=''（'world' をそのまま送らない）。"""
    mock_instance = _mock_trendreq(mock_trendreq, _mock_trends_df())

    fetch_google_trends("Python", geo=geo)

    assert mock_instance.build_payload.call_args[1]["geo"] == ""


@patch("trends_fetcher.TrendReq")
def test_fetch_trends_empty_data_no_csv(mock_trendreq: MagicMock, tmp_path: Path) -> None:
    """データが空のときCSVを生成せず空DFを返す。"""
    _mock_trendreq(mock_trendreq, pd.DataFrame())

    out = str(tmp_path / "trends_empty.csv")
    df = fetch_google_trends("Python", output_file=out)

    assert not Path(out).exists()
    assert df.is_empty()


@patch("trends_fetcher.TrendReq")
def test_fetch_trends_api_error_raises(mock_trendreq: MagicMock, tmp_path: Path) -> None:
    """pytrends例外（429等）は握り潰さず送出し、CSVも作らない。"""
    mock_instance = MagicMock()
    mock_instance.interest_over_time.side_effect = Exception("429 Too Many Requests")
    mock_trendreq.return_value = mock_instance

    out = str(tmp_path / "trends_err.csv")
    with pytest.raises(Exception, match="429"):
        fetch_google_trends("Python", output_file=out)

    assert not Path(out).exists()


@patch("trends_fetcher.TrendReq")
def test_no_output_file_writes_nothing(
    mock_trendreq: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_trendreq(mock_trendreq, _mock_trends_df())
    monkeypatch.chdir(tmp_path)

    fetch_google_trends("Python")

    assert list(tmp_path.iterdir()) == []


@patch("trends_fetcher.TrendReq")
def test_hub_get_trends(mock_trendreq: MagicMock, hub) -> None:
    _mock_trendreq(mock_trendreq, _mock_trends_df(last_partial=True))

    df = hub.get_trends(["Python", "Rust"])

    assert "date" in df.columns
    assert df.height == 3
