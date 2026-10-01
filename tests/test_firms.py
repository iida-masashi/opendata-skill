"""Tests for firms_fetcher.py (NASA_FIRMS_API_KEY未設定想定 → モック中心)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


from firms_fetcher import RISK_REGIONS, SOURCES, fetch_firms_data


def test_regions_defined() -> None:
    for r in ["us_west", "california", "australia", "japan"]:
        assert r in RISK_REGIONS
        parts = RISK_REGIONS[r].split(",")
        assert len(parts) == 4


def test_sources_defined() -> None:
    for s in ["modis", "viirs_s", "viirs_n", "landsat"]:
        assert s in SOURCES


FIRMS_CSV_SAMPLE = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight\n"
    "38.5,-120.3,345.1,0.5,0.5,2026-04-10,1230,N,nominal,2.0NRT,295.2,42.5,D\n"
    "39.0,-121.1,355.2,0.5,0.5,2026-04-11,0115,N,high,2.0NRT,298.5,55.3,N\n"
)


@patch("firms_fetcher.requests.get")
def test_mock_firms_csv(mock_get: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """モック: FIRMS CSV レスポンスをパース。"""
    monkeypatch.setenv("NASA_FIRMS_API_KEY", "test_key_mock")

    mock_resp = MagicMock()
    mock_resp.text = FIRMS_CSV_SAMPLE
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    out = str(tmp_path / "firms.csv")
    df = fetch_firms_data(region="us_west", source="viirs_n", day_range=5, output_file=out)
    assert df.height == 2
    # 標準化カラム
    assert "date" in df.columns
    assert "value" in df.columns
    assert "region" in df.columns
    assert Path(out).exists()


@pytest.mark.parametrize("body", [
    "Invalid MAP_KEY.",
    "Exceeding allowed transaction limit.",
    "",
])
@patch("firms_fetcher.requests.get")
def test_mock_error_text_raises(
    mock_get: MagicMock, body: str, make_response, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HTTP 200 で返るエラー文（'Invalid' 始まり以外も含む）・空ボディは空DFに化けず例外。"""
    monkeypatch.setenv("NASA_FIRMS_API_KEY", "test_key_mock")
    mock_get.return_value = make_response(text=body)

    with pytest.raises(RuntimeError, match="FIRMS"):
        fetch_firms_data(region="us_west")


@patch("firms_fetcher.requests.get")
def test_mock_empty_csv(mock_get: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    """空のCSV（ヘッダのみ）は正常な0件として空DF。"""
    monkeypatch.setenv("NASA_FIRMS_API_KEY", "test_key_mock")

    mock_resp = MagicMock()
    mock_resp.text = "latitude,longitude,bright_ti4\n"
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    df = fetch_firms_data(region="us_west")
    assert df.is_empty()


@pytest.mark.parametrize("day_range", [0, 6, 20])
def test_day_range_out_of_range_raises(day_range: int, monkeypatch: pytest.MonkeyPatch) -> None:
    """day_range が API の許容範囲 (1..5) 外なら黙って丸めず ValueError。"""
    monkeypatch.setenv("NASA_FIRMS_API_KEY", "test_key_mock")
    with pytest.raises(ValueError, match="day_range"):
        fetch_firms_data(region="us_west", day_range=day_range)


@patch("firms_fetcher.requests.get")
def test_mock_http_error_raises_and_redacts_key(
    mock_get: MagicMock, make_response, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HTTP エラーは例外。URL パスに入る MAP_KEY をメッセージ・出力に出さない。"""
    import requests
    monkeypatch.setenv("NASA_FIRMS_API_KEY", "SECRET_FIRMS_KEY")
    mock_get.return_value = make_response(
        text="Forbidden", status=403,
        url="https://firms.modaps.eosdis.nasa.gov/api/area/csv/SECRET_FIRMS_KEY/VIIRS_NOAA20_NRT/x/1",
    )

    with pytest.raises(requests.exceptions.HTTPError) as exc_info:
        fetch_firms_data(region="california", day_range=1)
    assert "403" in str(exc_info.value)
    assert "SECRET_FIRMS_KEY" not in str(exc_info.value)


@patch("firms_fetcher.requests.get")
def test_connection_error_redacts_key(mock_get: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    """接続系エラーのメッセージ（URL を含む）からも MAP_KEY を伏せる。"""
    import requests
    monkeypatch.setenv("NASA_FIRMS_API_KEY", "SECRET_FIRMS_KEY")
    mock_get.side_effect = requests.exceptions.InvalidURL(
        "Invalid URL: /api/area/csv/SECRET_FIRMS_KEY/VIIRS_NOAA20_NRT/x/1"
    )

    with pytest.raises(requests.exceptions.InvalidURL) as exc_info:
        fetch_firms_data(region="california", day_range=1)
    assert "SECRET_FIRMS_KEY" not in str(exc_info.value)
