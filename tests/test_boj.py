"""Tests for boj_fetcher.py (BOJ Time-Series Data Search API — TANKAN)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


from boj_fetcher import SERIES_ALIAS, fetch_boj_data

# Real BOJ getDataCode CSV: a metadata preamble precedes the SERIES_CODE header.
MOCK_CSV = (
    "STATUS,200\n"
    "MESSAGEID,\n"
    "PARAMETER,db=CO\n"
    "NEXTPOSITION,\n"
    "SERIES_CODE,NAME_OF_TIME_SERIES,UNIT,FREQUENCY,CATEGORY,LAST_UPDATE,SURVEY_DATES,VALUES\n"
    "TK99F1000601GCQ01000,Large mfg DI,DI,Q,TANKAN,2026-04-01,202504,12\n"
    "TK99F1000601GCQ01000,Large mfg DI,DI,Q,TANKAN,2026-04-01,202601,17\n"
)


@patch("boj_fetcher.requests.get")
def test_fetch_boj_parses_preamble_and_saves_csv(
    mock_get: MagicMock, tmp_path: Path
) -> None:
    resp = MagicMock()
    resp.text = MOCK_CSV
    resp.raise_for_status.return_value = None
    mock_get.return_value = resp

    out = str(tmp_path / "boj.csv")
    df = fetch_boj_data(series="tankan_large_mfg", output_file=out)

    assert Path(out).exists()
    assert not df.is_empty()
    # date / value normalized; preamble skipped (no STATUS row leaked in)
    assert "date" in df.columns
    assert "value" in df.columns
    assert df.height == 2
    assert "STATUS" not in df["date"].to_list()
    # values parsed
    assert 17 in df["value"].to_list()


@patch("boj_fetcher.requests.get")
def test_fetch_boj_alias_resolves_to_series_code(
    mock_get: MagicMock, tmp_path: Path
) -> None:
    resp = MagicMock()
    resp.text = MOCK_CSV
    resp.raise_for_status.return_value = None
    mock_get.return_value = resp

    fetch_boj_data(series="tankan_large_mfg", output_file=str(tmp_path / "o.csv"))
    params = mock_get.call_args[1]["params"]
    assert params["code"] == SERIES_ALIAS["tankan_large_mfg"]
    assert params["db"] == "CO"
    assert params["format"] == "csv"


@patch("boj_fetcher.requests.get")
def test_fetch_boj_passes_raw_code_when_not_alias(
    mock_get: MagicMock, tmp_path: Path
) -> None:
    resp = MagicMock()
    resp.text = MOCK_CSV
    resp.raise_for_status.return_value = None
    mock_get.return_value = resp

    fetch_boj_data(series="TK99F0000601GCQ01000", output_file=str(tmp_path / "o.csv"))
    assert mock_get.call_args[1]["params"]["code"] == "TK99F0000601GCQ01000"


@patch("boj_fetcher.requests.get")
def test_fetch_boj_empty_body_no_crash(mock_get: MagicMock, tmp_path: Path) -> None:
    resp = MagicMock()
    resp.text = "STATUS,200\nNEXTPOSITION,\n"  # no data rows
    resp.raise_for_status.return_value = None
    mock_get.return_value = resp

    out = str(tmp_path / "empty.csv")
    df = fetch_boj_data(series="tankan_large_mfg", output_file=out)
    assert df.is_empty()
    assert not Path(out).exists()


@patch("boj_fetcher.requests.get")
def test_fetch_boj_json_error_body_raises(mock_get: MagicMock, make_response) -> None:
    """format=csv でもエラー時は JSON で返る（BOJ API マニュアル）。空DFに化けず送出する。"""
    mock_get.return_value = make_response(
        json={"STATUS": 400, "MESSAGEID": "M181013E", "MESSAGE": "指定した系列コードは存在しません。：1番目のコード"}
    )
    with pytest.raises(RuntimeError, match="M181013E"):
        fetch_boj_data(series="TKXXXX")


@patch("boj_fetcher.requests.get")
def test_fetch_boj_csv_status_not_200_raises(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(text="STATUS,503\nMESSAGEID,M181091S\nMESSAGE,DB error\n")
    with pytest.raises(RuntimeError, match="503"):
        fetch_boj_data(series="tankan_large_mfg")


@patch("boj_fetcher.requests.get")
def test_fetch_boj_unrecognized_body_raises(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(text="<html>maintenance</html>")
    with pytest.raises(RuntimeError):
        fetch_boj_data(series="tankan_large_mfg")


@patch("boj_fetcher.requests.get")
def test_fetch_boj_http_error_propagates(mock_get: MagicMock, make_response) -> None:
    """以前は except Exception で空DFを返していた。"""
    import requests
    mock_get.return_value = make_response(status=404)
    with pytest.raises(requests.exceptions.HTTPError):
        fetch_boj_data(series="tankan_large_mfg")


@patch("boj_fetcher.requests.get")
def test_fetch_boj_follows_nextposition(mock_get: MagicMock, make_response) -> None:
    """NEXTPOSITION に数値があれば startPosition を付けて続きを取得し、結合する。"""
    header = "SERIES_CODE,NAME_OF_TIME_SERIES,UNIT,FREQUENCY,CATEGORY,LAST_UPDATE,SURVEY_DATES,VALUES\n"
    page1 = "STATUS,200\nMESSAGEID,M181000I\nNEXTPOSITION,2\n" + header + "A,a,DI,Q,T,20260401,202501,1\n"
    page2 = "STATUS,200\nMESSAGEID,M181000I\nNEXTPOSITION,\n" + header + "B,b,DI,Q,T,20260401,202501,2\n"
    mock_get.side_effect = [make_response(text=page1), make_response(text=page2)]

    df = fetch_boj_data(series="A,B")
    assert df["SERIES_CODE"].to_list() == ["A", "B"]
    assert mock_get.call_count == 2
    assert "startPosition" not in mock_get.call_args_list[0].kwargs["params"]
    assert mock_get.call_args_list[1].kwargs["params"]["startPosition"] == "2"


@patch("boj_fetcher.requests.get")
def test_fetch_boj_http_error_keeps_api_message(mock_get: MagicMock, make_response) -> None:
    """実 API はエラー時 HTTP 400 + JSON 本文を返す。MESSAGEID を例外メッセージに残す。"""
    import requests
    mock_get.return_value = make_response(
        json={"STATUS": 400, "MESSAGEID": "M181013E", "MESSAGE": "Series code does not exist"}, status=400
    )
    with pytest.raises(requests.exceptions.HTTPError, match="M181013E"):
        fetch_boj_data(series="TKXXXX")
