"""Tests for estat_id_searcher.py (e-Stat getStatsList, モック)."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from estat_id_searcher import search_estat_list


def _list_payload(table_inf):
    return {
        "GET_STATS_LIST": {
            "RESULT": {"STATUS": 0, "ERROR_MSG": "正常に終了しました。"},
            "DATALIST_INF": {"NUMBER": 1, "TABLE_INF": table_inf},
        }
    }


@patch("estat_id_searcher.requests.get")
def test_search_single_result_dict_normalized(mock_get: MagicMock, make_response) -> None:
    """TABLE_INF が1件だと dict で返る → list に正規化して DataFrame にする。"""
    mock_get.return_value = make_response(
        json=_list_payload({"@id": "0003446461", "TITLE_SPEC": {"TABLE_NAME": "景気動向指数"}})
    )
    df = search_estat_list("dummy", "景気")
    assert df.to_dicts() == [{"id": "0003446461", "title": "景気動向指数"}]
    assert mock_get.call_args[0][0].startswith("https://")
    assert mock_get.call_args.kwargs["timeout"] > 0


@patch("estat_id_searcher.requests.get")
def test_search_no_data_status_returns_empty(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(json={"GET_STATS_LIST": {"RESULT": {"STATUS": 1}}})
    assert search_estat_list("dummy", "存在しない").is_empty()


@patch("estat_id_searcher.requests.get")
def test_search_api_error_raises(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(
        json={"GET_STATS_LIST": {"RESULT": {"STATUS": 100, "ERROR_MSG": "認証に失敗しました。"}}}
    )
    with pytest.raises(RuntimeError, match="認証に失敗"):
        search_estat_list("bad", "x")


@patch("estat_id_searcher.requests.get")
def test_search_http_error_propagates(mock_get: MagicMock, make_response) -> None:
    """以前は例外を print して None を返していた。"""
    mock_get.return_value = make_response(status=403)
    with pytest.raises(requests.exceptions.HTTPError):
        search_estat_list("dummy", "x")
