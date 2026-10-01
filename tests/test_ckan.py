"""Tests for ckan_fetcher.py (CKAN open data portal search)."""
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from ckan_fetcher import search_ckan


def _make_ckan_response(num_results: int = 2) -> dict[str, Any]:
    """CKANのpackage_searchレスポンスを生成する。"""
    packages = []
    for i in range(num_results):
        packages.append({
            "title": f"Dataset {i}",
            "organization": {"title": f"Org {i}"},
            "resources": [
                {
                    "name": f"Resource {i}",
                    "format": "CSV",
                    "url": f"https://example.com/data_{i}.csv",
                    "description": f"Description {i}",
                    "last_modified": "2024-01-01",
                },
                {
                    "name": f"Resource {i} PDF",
                    "format": "PDF",
                    "url": f"https://example.com/doc_{i}.pdf",
                    "description": None,
                    "last_modified": None,
                },
            ],
        })
    return {"success": True, "result": {"results": packages}}


@patch("ckan_fetcher.requests.get")
def test_search_saves_csv_resources(mock_get: MagicMock, tmp_path: Path) -> None:
    """正常系: CSV形式のリソース一覧をCSVに保存する。"""
    mock_response = MagicMock()
    mock_response.json.return_value = _make_ckan_response(2)
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    out = str(tmp_path / "ckan_test.csv")
    search_ckan("https://data.e-gov.go.jp/data", "AED", rows=10, output_file=out)

    assert Path(out).exists()
    content = Path(out).read_text(encoding="utf-8")
    assert "Dataset" in content
    assert "example.com" in content


@patch("ckan_fetcher.requests.get")
def test_search_filters_out_non_csv(mock_get: MagicMock, tmp_path: Path) -> None:
    """CSVフォーマット以外のリソースは含まれない。"""
    mock_response = MagicMock()
    mock_response.json.return_value = _make_ckan_response(1)
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    out = str(tmp_path / "ckan_filter.csv")
    search_ckan("https://data.e-gov.go.jp/data", "AED", output_file=out)

    content = Path(out).read_text(encoding="utf-8")
    assert ".pdf" not in content


@patch("ckan_fetcher.requests.get")
def test_search_no_results_no_csv(mock_get: MagicMock, tmp_path: Path) -> None:
    """検索結果が0件のときCSVを生成しない。"""
    mock_response = MagicMock()
    mock_response.json.return_value = {"success": True, "result": {"results": []}}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    out = str(tmp_path / "ckan_empty.csv")
    df = search_ckan("https://data.e-gov.go.jp/data", "NOTFOUND", output_file=out)

    assert df.is_empty()  # 正常応答で0件は空DF（失敗ではない）
    assert not Path(out).exists()


@patch("ckan_fetcher.requests.get")
def test_search_api_failure_raises(mock_get: MagicMock, tmp_path: Path) -> None:
    """CKAN APIがsuccess=Falseのときは例外にする（以前は空で返っていた）。"""
    mock_response = MagicMock()
    mock_response.json.return_value = {"success": False, "error": {"message": "Search error"}}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    out = str(tmp_path / "ckan_fail.csv")
    with pytest.raises(RuntimeError, match="Search error"):
        search_ckan("https://data.e-gov.go.jp/data", "query", output_file=out)

    assert not Path(out).exists()


@patch("ckan_fetcher.requests.get")
def test_search_network_error_raises(mock_get: MagicMock, tmp_path: Path) -> None:
    """ネットワークエラーは握り潰さず送出する。"""
    mock_get.side_effect = ValueError("Network error")

    out = str(tmp_path / "ckan_net.csv")
    with pytest.raises(ValueError, match="Network error"):
        search_ckan("https://data.e-gov.go.jp/data", "query", output_file=out)

    assert not Path(out).exists()


@patch("ckan_fetcher.requests.get")
def test_search_constructs_correct_api_url(mock_get: MagicMock, tmp_path: Path) -> None:
    """/api/3/action/package_search エンドポイントを呼ぶ。"""
    mock_response = MagicMock()
    mock_response.json.return_value = _make_ckan_response(1)
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    search_ckan("https://data.e-gov.go.jp/data", "test", output_file=str(tmp_path / "out.csv"))

    called_url = mock_get.call_args[0][0]
    assert "package_search" in called_url


@patch("ckan_fetcher.requests.get")
def test_search_null_organization_and_format(mock_get: MagicMock) -> None:
    """organization / format が null のパッケージで AttributeError にならない。"""
    mock_response = MagicMock()
    mock_response.json.return_value = {"success": True, "result": {"results": [
        {"title": "No org", "organization": None, "resources": [
            {"name": "r0", "format": None, "url": "https://example.com/a"},
            {"name": "r1", "format": "csv", "url": "https://example.com/b.csv"},
        ]},
    ]}}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    df = search_ckan("https://data.e-gov.go.jp/data", "x")

    assert df["Organization"].to_list() == [None]
    assert df["URL"].to_list() == ["https://example.com/b.csv"]
