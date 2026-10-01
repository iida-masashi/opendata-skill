"""Tests for corp_fetcher.py (国税庁 法人番号 Web-API Ver.4)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

import corp_fetcher
from corp_fetcher import fetch_corporate_info


def _xml(header: str, corps: list[str]) -> bytes:
    body = "".join(f"<corporation>{c}</corporation>" for c in corps)
    return f'<?xml version="1.0" encoding="UTF-8"?><corporations>{header}{body}</corporations>'.encode()


def _header(count: int, divide_number: int, divide_size: int) -> str:
    return (
        "<lastUpdateDate>2024-01-01</lastUpdateDate>"
        f"<count>{count}</count><divideNumber>{divide_number}</divideNumber>"
        f"<divideSize>{divide_size}</divideSize>"
    )


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORP_API_KEY", "dummy")


@patch("corp_fetcher.requests.get")
def test_name_search_fetches_all_divided_pages(mock_get: MagicMock, make_response) -> None:
    """仕様: 法人名検索は 2,000 件超で分割される。divide を divideSize まで回して全件取る。"""
    pages = {
        None: _xml(_header(3, 1, 2), ["<corporateNumber>1</corporateNumber>", "<corporateNumber>2</corporateNumber>"]),
        "2": _xml(_header(3, 2, 2), ["<corporateNumber>3</corporateNumber>"]),
    }

    def _get(url: str, **kwargs):
        return make_response(content=pages[kwargs["params"].get("divide")])

    mock_get.side_effect = _get

    df = fetch_corporate_info("テスト", mode="name")

    assert df["corporateNumber"].to_list() == ["1", "2", "3"]
    assert mock_get.call_count == 2


@patch("corp_fetcher.requests.get")
def test_number_search_never_sends_divide(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(
        content=_xml(_header(1, 1, 1), ["<corporateNumber>1234567890123</corporateNumber>"])
    )

    df = fetch_corporate_info("1234567890123", mode="number")

    assert df.height == 1
    assert mock_get.call_count == 1
    assert "divide" not in mock_get.call_args[1]["params"]


@patch("corp_fetcher.requests.get")
def test_keys_beyond_first_100_records_are_kept(mock_get: MagicMock, make_response) -> None:
    """先頭100件に無いタグ（例: closeDate）も列として残る（polars のスキーマ推論が100行で打ち切らない）。"""
    corps = ["<corporateNumber>1</corporateNumber>"] * 100
    corps.append("<corporateNumber>2</corporateNumber><closeDate>2024-01-01</closeDate>")
    mock_get.return_value = make_response(content=_xml(_header(101, 1, 1), corps))

    df = fetch_corporate_info("株式会社", mode="name")

    assert "closeDate" in df.columns
    assert df["closeDate"].to_list()[-1] == "2024-01-01"


@patch("corp_fetcher.requests.get")
def test_http_error_raises(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(status=404, text="")

    with pytest.raises(requests.exceptions.HTTPError):
        fetch_corporate_info("1234567890123")


@patch("corp_fetcher.requests.get")
def test_no_output_file_does_not_write_to_cwd(
    mock_get: MagicMock, make_response, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    mock_get.return_value = make_response(
        content=_xml(_header(1, 1, 1), ["<corporateNumber>1</corporateNumber>"])
    )

    df = fetch_corporate_info("1234567890123")

    assert df.height == 1
    assert list(tmp_path.iterdir()) == []


@patch("corp_fetcher.requests.get")
def test_cli_default_filename_escapes_slash(
    mock_get: MagicMock, make_response, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """社名に '/' を含んでも既定の出力ファイル名で保存に失敗しない。"""
    monkeypatch.chdir(tmp_path)
    mock_get.return_value = make_response(
        content=_xml(_header(1, 1, 1), ["<corporateNumber>1</corporateNumber>"])
    )
    monkeypatch.setattr("sys.argv", ["corp_fetcher.py", "A/B 商事", "--name"])

    corp_fetcher.main()

    files = list(tmp_path.iterdir())
    assert len(files) == 1
    assert files[0].name.startswith("corp_")
