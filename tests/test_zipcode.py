"""Tests for zipcode_fetcher.py (ZipCloud API)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zipcode_fetcher import fetch_zipcode

MOCK_SUCCESS_RESPONSE = {
    "status": 200,
    "message": None,
    "results": [
        {
            "zipcode": "1000001",
            "prefcode": "13",
            "address1": "東京都",
            "address2": "千代田区",
            "address3": "千代田",
            "kana1": "トウキョウト",
            "kana2": "チヨダク",
            "kana3": "チヨダ",
        }
    ],
}

MOCK_NOT_FOUND_RESPONSE = {
    "status": 200,
    "message": None,
    "results": None,
}

MOCK_API_ERROR_RESPONSE = {
    "status": 400,
    "message": "Invalid zipcode format.",
    "results": None,
}


@patch("zipcode_fetcher.requests.get")
def test_fetch_valid_zipcode_saves_csv(mock_get: MagicMock, tmp_path: Path) -> None:
    """正常系: 有効な郵便番号でCSVを保存する。"""
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_SUCCESS_RESPONSE
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    out = str(tmp_path / "zipcode.csv")
    fetch_zipcode("1000001", output_file=out)

    assert Path(out).exists()
    content = Path(out).read_text(encoding="utf-8")
    assert "zipcode" in content
    assert "1000001" in content


@patch("zipcode_fetcher.requests.get")
def test_fetch_correct_api_url(mock_get: MagicMock, tmp_path: Path) -> None:
    """ZipCloud APIのURLにzipcodeパラメータを渡す。"""
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_SUCCESS_RESPONSE
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    fetch_zipcode("1000001", output_file=str(tmp_path / "out.csv"))

    call_kwargs = mock_get.call_args
    assert "zipcloud" in call_kwargs[0][0]
    assert call_kwargs[1]["params"]["zipcode"] == "1000001"


@patch("zipcode_fetcher.requests.get")
def test_fetch_not_found_no_csv(mock_get: MagicMock, tmp_path: Path) -> None:
    """該当なしの場合はCSVを生成しない。"""
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_NOT_FOUND_RESPONSE
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    out = str(tmp_path / "zipcode_none.csv")
    df = fetch_zipcode("9999999", output_file=out)

    assert df.is_empty()  # 正常応答で0件は空DF（失敗ではない）
    assert not Path(out).exists()


@patch("zipcode_fetcher.requests.get")
def test_fetch_api_status_error_raises(mock_get: MagicMock, tmp_path: Path) -> None:
    """HTTP 200 + status!=200（入力エラー等）は例外にする（以前は空で返っていた）。"""
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_API_ERROR_RESPONSE
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    out = str(tmp_path / "zipcode_err.csv")
    with pytest.raises(ValueError, match="Invalid zipcode format"):
        fetch_zipcode("INVALID", output_file=out)

    assert not Path(out).exists()


@patch("zipcode_fetcher.requests.get")
def test_fetch_network_error_raises(mock_get: MagicMock, tmp_path: Path) -> None:
    """ネットワークエラーは握り潰さず送出する。"""
    mock_get.side_effect = ValueError("Network unreachable")

    out = str(tmp_path / "zipcode_net.csv")
    with pytest.raises(ValueError, match="Network unreachable"):
        fetch_zipcode("1000001", output_file=out)

    assert not Path(out).exists()
