"""Tests for trends_fetcher.py (Google Trends via pytrends)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import polars as pl
import pytest
import requests
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


def _real_trendreq_session(monkeypatch: pytest.MonkeyPatch, responses: list) -> list:
    """TrendReq は本物のまま、Cookie取得と HTTP 送信だけ差し替える（送信順に responses を返す）。"""
    from pytrends.request import TrendReq

    monkeypatch.setattr(TrendReq, "GetGoogleCookie", lambda self: {})
    for r in responses:
        r.headers["Content-Type"] = "text/html"  # pytrends は非200でも Content-Type を参照する
    calls: list = []

    def _send(self, url, **kwargs):
        calls.append(url)
        return responses[min(len(calls), len(responses)) - 1]

    monkeypatch.setattr(requests.Session, "get", _send)
    monkeypatch.setattr(requests.Session, "post", _send)
    return calls


def test_real_trendreq_429_is_retried_not_typeerror(
    monkeypatch: pytest.MonkeyPatch, make_response
) -> None:
    """本物の TrendReq 経路で 429 は共通リトライに乗り、最終的に HTTPError(429) を送出する。

    pytrends 内蔵リトライ（retries>0）は urllib3 2.x で削除された method_whitelist を使い
    TypeError になるため使わない（回帰テスト）。
    """
    calls = _real_trendreq_session(monkeypatch, [make_response(text="", status=429)])

    with pytest.raises(requests.exceptions.HTTPError, match="429"):
        fetch_google_trends("Python")

    assert len(calls) == 5  # retry_with_ratelimit の stop_after_attempt(5)


def test_real_trendreq_4xx_fails_fast(monkeypatch: pytest.MonkeyPatch, make_response) -> None:
    """429 以外の 4xx はリトライせず即失敗する。"""
    calls = _real_trendreq_session(monkeypatch, [make_response(text="", status=400)])

    with pytest.raises(requests.exceptions.HTTPError, match="400"):
        fetch_google_trends("Python")

    assert len(calls) == 1


@patch("trends_fetcher.TrendReq")
def test_second_resolution_index_converts_without_pyarrow(mock_trendreq: MagicMock) -> None:
    """pandas 3 の pytrends は日付を datetime64[s] で返す。pl.from_pandas は pyarrow 無しだと
    これを変換できないため、pyarrow 非依存で date 列を組み立てる。"""
    df = _mock_trends_df()
    df.index = df.index.astype("datetime64[s]")
    _mock_trendreq(mock_trendreq, df)

    out = fetch_google_trends(["Python", "Rust"])

    assert out.columns == ["date", "Python", "Rust"]
    assert out.schema["date"] == pl.Datetime
    assert out["date"][0].isoformat() == "2024-01-07T00:00:00"
