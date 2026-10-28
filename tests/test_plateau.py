"""Tests for plateau_fetcher.py (G空間情報センター CKAN の PLATEAU パッケージ検索)."""
from unittest.mock import MagicMock, patch

import pytest
from plateau_fetcher import fetch_plateau_model


def _pkg(title: str, name: str, url: str) -> dict:
    return {"title": title, "name": name, "resources": [
        {"name": "CityGML", "format": "ZIP", "url": url, "description": None},
    ]}


def _search(results: list[dict]) -> dict:
    return {"success": True, "result": {"count": len(results), "results": results}}


# 2026-10 時点の実際の検索結果（「PLATEAU 府中市」）: 広島県府中市が先頭に来る。
FUCHU = [
    _pkg("3D都市モデル（Project PLATEAU）府中市（2022年度）", "plateau-34208-fuchu-shi-2022", "https://e/34208-2022.zip"),
    _pkg("3D都市モデル（Project PLATEAU）府中市（2025年度）", "plateau-13206-fuchu-shi-2025", "https://e/13206-2025.zip"),
    _pkg("3D都市モデル（Project PLATEAU）府中市（2023年度）", "plateau-13206-fuchu-shi-2023", "https://e/13206-2023.zip"),
]
CHIYODA = [
    _pkg("3D都市モデル（Project PLATEAU）千代田区（2023年度）", "plateau-13101-chiyoda-ku-2023", "https://e/13101-2023.zip"),
    _pkg("3D都市モデル（Project PLATEAU）千代田区（2025年度）", "plateau-13101-chiyoda-ku-2025", "https://e/13101-2025.zip"),
]


@patch("plateau_fetcher.requests.get")
def test_ambiguous_city_name_raises(mock_get: MagicMock, make_response) -> None:
    """同名の別自治体（広島県/東京都 府中市）を1件目で黙って採用していた。"""
    mock_get.return_value = make_response(json=_search(FUCHU))

    with pytest.raises(ValueError, match="34208.*13206|13206.*34208"):
        fetch_plateau_model("府中市")


@patch("plateau_fetcher.requests.get")
def test_city_code_query_raises(mock_get: MagicMock) -> None:
    """コード検索は全文検索で常に0件（実測）になり、空DFに化けていた。"""
    with pytest.raises(ValueError, match="自治体名"):
        fetch_plateau_model("13101")
    mock_get.assert_not_called()


@patch("plateau_fetcher.requests.get")
def test_latest_year_of_matching_city(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(json=_search(CHIYODA))

    df = fetch_plateau_model("千代田区")

    assert df["url"].to_list() == ["https://e/13101-2025.zip"]


@patch("plateau_fetcher.requests.get")
def test_no_matching_city_raises(mock_get: MagicMock, make_response) -> None:
    """全文検索がヒットしても自治体名が一致しなければ採用しない。"""
    mock_get.return_value = make_response(json=_search(CHIYODA))

    with pytest.raises(ValueError, match="千代田"):
        fetch_plateau_model("代田")


@patch("plateau_fetcher.requests.get")
def test_no_results_returns_empty(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(json=_search([]))

    assert fetch_plateau_model("存在しない市").is_empty()


@pytest.mark.parametrize(
    ("query", "expected_url"),
    [
        ("東京都府中市", "https://e/13206-2025.zip"),
        ("東京都 府中市", "https://e/13206-2025.zip"),
        ("広島県府中市", "https://e/34208-2022.zip"),
    ],
)
@patch("plateau_fetcher.requests.get")
def test_prefecture_prefix_disambiguates_same_name_city(
    mock_get: MagicMock, make_response, query: str, expected_url: str
) -> None:
    """都道府県名併記で同名自治体を一意に選択でき、CKAN検索クエリには自治体名のみ渡す。"""
    mock_get.return_value = make_response(json=_search(FUCHU))

    df = fetch_plateau_model(query)

    assert mock_get.call_args.kwargs["params"]["q"] == "PLATEAU 府中市"
    assert df["url"].to_list() == [expected_url]


@pytest.mark.parametrize(
    ("code", "expected_url"),
    [
        ("13206", "https://e/13206-2025.zip"),
        ("132060", "https://e/13206-2025.zip"),  # 6桁（チェックディジット付き）
        ("34208", "https://e/34208-2022.zip"),
    ],
)
@patch("plateau_fetcher.requests.get")
def test_city_code_argument_disambiguates_same_name_city(
    mock_get: MagicMock, make_response, code: str, expected_url: str
) -> None:
    """5桁・6桁の全国地方公共団体コード指定で同名自治体を一意に選択できる。"""
    mock_get.return_value = make_response(json=_search(FUCHU))

    df = fetch_plateau_model("府中市", code=code)

    assert df["url"].to_list() == [expected_url]


@patch("plateau_fetcher.requests.get")
def test_invalid_city_code_format_raises(mock_get: MagicMock) -> None:
    with pytest.raises(ValueError, match="5桁または6桁"):
        fetch_plateau_model("府中市", code="132")
    mock_get.assert_not_called()
