"""Tests for trends_fetcher.py (Google Trends via pytrends)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from trends_fetcher import fetch_google_trends


def _mock_trends_df() -> pd.DataFrame:
    """pytrends.interest_over_time()が返すようなDataFrameを生成する。"""
    dates = pd.date_range("2024-01-01", periods=4, freq="W")
    df = pd.DataFrame(
        {"Python": [80, 85, 78, 90], "Rust": [30, 35, 32, 40], "isPartial": [False] * 4},
        index=dates,
    )
    df.index.name = "date"
    return df


@patch("trends_fetcher.TrendReq")
def test_fetch_trends_saves_csv(mock_trendreq: MagicMock, tmp_path: Path) -> None:
    """正常系: Google TrendsデータをCSVに保存する。"""
    mock_instance = MagicMock()
    mock_instance.interest_over_time.return_value = _mock_trends_df()
    mock_trendreq.return_value = mock_instance

    out = str(tmp_path / "trends_test.csv")
    fetch_google_trends("Python,Rust", output_file=out)

    assert Path(out).exists()
    content = Path(out).read_text()
    assert "Python" in content
    assert "Rust" in content


@patch("trends_fetcher.TrendReq")
def test_fetch_trends_removes_ispartial(mock_trendreq: MagicMock, tmp_path: Path) -> None:
    """isPartial列が出力CSVに含まれない。"""
    mock_instance = MagicMock()
    mock_instance.interest_over_time.return_value = _mock_trends_df()
    mock_trendreq.return_value = mock_instance

    out = str(tmp_path / "trends_partial.csv")
    fetch_google_trends(["Python"], output_file=out)

    content = Path(out).read_text()
    assert "isPartial" not in content


@patch("trends_fetcher.TrendReq")
def test_fetch_trends_string_keywords_split(mock_trendreq: MagicMock, tmp_path: Path) -> None:
    """カンマ区切り文字列をリストに分割してbuild_payloadに渡す。"""
    mock_instance = MagicMock()
    mock_instance.interest_over_time.return_value = _mock_trends_df()
    mock_trendreq.return_value = mock_instance

    fetch_google_trends("Python,Rust", output_file=str(tmp_path / "t.csv"))

    call_args = mock_instance.build_payload.call_args[0]
    assert "Python" in call_args[0]
    assert "Rust" in call_args[0]


@patch("trends_fetcher.TrendReq")
def test_fetch_trends_empty_data_no_csv(mock_trendreq: MagicMock, tmp_path: Path) -> None:
    """データが空のときCSVを生成しない。"""
    mock_instance = MagicMock()
    mock_instance.interest_over_time.return_value = pd.DataFrame()
    mock_trendreq.return_value = mock_instance

    out = str(tmp_path / "trends_empty.csv")
    fetch_google_trends("Python", output_file=out)

    assert not Path(out).exists()


@patch("trends_fetcher.TrendReq")
def test_fetch_trends_api_error_no_crash(mock_trendreq: MagicMock, tmp_path: Path) -> None:
    """pytrends例外時にクラッシュしない。"""
    mock_instance = MagicMock()
    mock_instance.interest_over_time.side_effect = Exception("429 Too Many Requests")
    mock_trendreq.return_value = mock_instance

    out = str(tmp_path / "trends_err.csv")
    fetch_google_trends("Python", output_file=out)

    assert not Path(out).exists()
