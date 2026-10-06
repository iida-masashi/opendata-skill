"""Tests for trends_fetcher.py (Google Trends via trendspyg)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest
import requests
from trends_fetcher import fetch_google_trends
from trendspyg import RateLimitError

_DATES = ["2024-01-07T00:00:00+00:00", "2024-01-14T00:00:00+00:00",
          "2024-01-21T00:00:00+00:00", "2024-01-28T00:00:00+00:00"]
_VALUES = {"Python": [80, 85, 78, 90], "Rust": [30, 35, 32, 40]}


def _comparison(keywords: list[str], last_partial: bool = False) -> dict:
    """trendspyg.download_google_trends_comparison(output_format='dict') と同じ形。"""
    rows = [
        {"date": d, "values": {kw: _VALUES[kw][i] for kw in keywords},
         "is_partial": last_partial and i == len(_DATES) - 1}
        for i, d in enumerate(_DATES)
    ]
    return {"keywords": keywords, "interest_over_time": rows}


def _single(keyword: str, last_partial: bool = False) -> list[dict]:
    """trendspyg.download_google_trends_interest_over_time(output_format='dict') と同じ形。"""
    return [
        {"date": d, "value": _VALUES[keyword][i], "is_partial": last_partial and i == len(_DATES) - 1}
        for i, d in enumerate(_DATES)
    ]


@patch("trends_fetcher.download_google_trends_comparison")
def test_fetch_trends_saves_csv(mock_cmp: MagicMock, tmp_path: Path) -> None:
    """正常系: Google TrendsデータをCSVに保存する。"""
    mock_cmp.return_value = _comparison(["Python", "Rust"])

    out = str(tmp_path / "trends_test.csv")
    fetch_google_trends("Python,Rust", output_file=out)

    content = Path(out).read_text()
    assert "Python" in content
    assert "Rust" in content
    assert "is_partial" not in content


@patch("trends_fetcher.download_google_trends_comparison")
def test_fetch_trends_returns_dataframe(mock_cmp: MagicMock) -> None:
    """戻り値は date 列付きの Polars DataFrame（date は UTC の naive datetime）。"""
    mock_cmp.return_value = _comparison(["Python", "Rust"])

    df = fetch_google_trends(["Python", "Rust"])

    assert isinstance(df, pl.DataFrame)
    assert df.columns == ["date", "Python", "Rust"]
    assert df.schema["date"] == pl.Datetime("us")
    assert df["date"][0].isoformat() == "2024-01-07T00:00:00"
    assert df["Python"].to_list() == [80, 85, 78, 90]
    assert df.height == 4


@patch("trends_fetcher.download_google_trends_comparison")
def test_fetch_trends_drops_partial_period_rows(mock_cmp: MagicMock) -> None:
    """is_partial=True（集計途中の最新期間）の行は値として残さず落とす。"""
    mock_cmp.return_value = _comparison(["Python", "Rust"], last_partial=True)

    df = fetch_google_trends(["Python", "Rust"])

    assert df.height == 3
    assert 90 not in df["Python"].to_list()


@patch("trends_fetcher.download_google_trends_comparison")
def test_multiple_keywords_use_comparison_over_http(mock_cmp: MagicMock) -> None:
    """2語以上は同一スケールの比較 API を、Chrome を起動しない http エンジンで呼ぶ。"""
    mock_cmp.return_value = _comparison(["Python", "Rust"])

    fetch_google_trends("Python, Rust", timeframe="today 3-m", geo="US")

    args, kwargs = mock_cmp.call_args
    assert args[0] == ["Python", "Rust"]
    assert kwargs["engine"] == "http"
    assert kwargs["timeframe"] == "today 3-m"
    assert kwargs["geo"] == "US"


@patch("trends_fetcher.download_google_trends_comparison")
@patch("trends_fetcher.download_google_trends_interest_over_time")
def test_single_keyword_uses_interest_over_time(mock_iot: MagicMock, mock_cmp: MagicMock) -> None:
    """1語は比較 API（2〜5語）ではなく単一キーワード API を http エンジンで呼ぶ。"""
    mock_iot.return_value = _single("Python", last_partial=True)

    df = fetch_google_trends("Python")

    mock_cmp.assert_not_called()
    assert mock_iot.call_args[0][0] == "Python"
    assert mock_iot.call_args[1]["engine"] == "http"
    assert df.columns == ["date", "Python"]
    assert df["Python"].to_list() == [80, 85, 78]


@pytest.mark.parametrize("geo", ["world", "WORLD", ""])
@patch("trends_fetcher.download_google_trends_interest_over_time")
def test_world_geo_maps_to_empty(mock_iot: MagicMock, geo: str) -> None:
    """Google Trends の全世界指定は geo=''（'world' をそのまま送らない）。"""
    mock_iot.return_value = _single("Python")

    fetch_google_trends("Python", geo=geo)

    assert mock_iot.call_args[1]["geo"] == ""


@patch("trends_fetcher.download_google_trends_interest_over_time")
def test_fetch_trends_empty_data_no_csv(mock_iot: MagicMock, tmp_path: Path) -> None:
    """データが空のときCSVを生成せず空DFを返す。"""
    mock_iot.return_value = []

    out = str(tmp_path / "trends_empty.csv")
    df = fetch_google_trends("Python", output_file=out)

    assert not Path(out).exists()
    assert df.is_empty()


@patch("trends_fetcher.download_google_trends_interest_over_time")
def test_fetch_trends_api_error_raises(mock_iot: MagicMock, tmp_path: Path) -> None:
    """trendspyg の例外（RateLimitError 等）は握り潰さず送出し、CSVも作らない。"""
    mock_iot.side_effect = RateLimitError("Google refused a direct Trends request (HTTP 429).")

    out = str(tmp_path / "trends_err.csv")
    with pytest.raises(RateLimitError, match="429"):
        fetch_google_trends("Python", output_file=out)

    assert not Path(out).exists()


@patch("trends_fetcher.download_google_trends_comparison")
def test_no_output_file_writes_nothing(
    mock_cmp: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_cmp.return_value = _comparison(["Python", "Rust"])
    monkeypatch.chdir(tmp_path)

    fetch_google_trends(["Python", "Rust"])

    assert list(tmp_path.iterdir()) == []


@patch("trends_fetcher.download_google_trends_comparison")
def test_hub_get_trends(mock_cmp: MagicMock, hub) -> None:
    mock_cmp.return_value = _comparison(["Python", "Rust"], last_partial=True)

    df = hub.get_trends(["Python", "Rust"])

    assert "date" in df.columns
    assert df.height == 3


def test_real_trendspyg_http_429_raises_once(
    monkeypatch: pytest.MonkeyPatch, make_response
) -> None:
    """本物の trendspyg http 経路で 429 は1回で RateLimitError になる（Chrome も再試行も無い）。"""
    from trendspyg.explore import _http

    monkeypatch.setattr(_http, "_session", None)
    monkeypatch.setattr(_http, "_paused_until", 0.0)
    calls: list = []

    def _request(self, method, url, **kwargs):
        calls.append(url)
        return make_response(text="", status=429, url=url)

    monkeypatch.setattr(requests.Session, "get", lambda self, url, **kw: make_response(text="", url=url))
    monkeypatch.setattr(requests.Session, "request", _request)

    with pytest.raises(RateLimitError, match="429"):
        fetch_google_trends("Python")

    assert len(calls) == 1


@pytest.mark.integration
def test_fetch_real_api() -> None:
    """実 Google Trends（trendspyg http エンジン）から日次データを取得できる。"""
    df = fetch_google_trends(["coffee", "tea"], timeframe="today 3-m", geo="JP")

    assert df.columns == ["date", "coffee", "tea"]
    assert df.height > 60
    assert df.schema["date"] == pl.Datetime("us")
    assert df["coffee"].max() <= 100
