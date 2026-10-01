"""Tests for youtube_fetcher.py (YouTube Data API v3 コメント)."""
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from youtube_fetcher import fetch_youtube_comments


def _item(text: str) -> dict:
    return {"snippet": {"topLevelComment": {"snippet": {
        "authorDisplayName": "a", "textDisplay": text, "likeCount": 1,
        "publishedAt": "2024-01-01T00:00:00Z",
    }}}}


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", "dummy")


@patch("youtube_fetcher.build")
def test_returns_dataframe_across_pages(mock_build: MagicMock) -> None:
    list_ = mock_build.return_value.commentThreads.return_value.list
    list_.return_value.execute.side_effect = [
        {"items": [_item("one")], "nextPageToken": "p2"},
        {"items": [_item("two")]},
    ]

    df = fetch_youtube_comments("vid", max_results=10)

    assert df["Text"].to_list() == ["one", "two"]
    assert list_.call_args_list[1][1]["pageToken"] == "p2"


@patch("youtube_fetcher.build")
def test_http_error_raises(mock_build: MagicMock) -> None:
    """コメント無効動画等の HttpError が「データ無し」に化けていた。"""
    resp = MagicMock(status=403, reason="Forbidden")
    mock_build.return_value.commentThreads.return_value.list.return_value.execute.side_effect = (
        HttpError(resp, b'{"error": {"message": "commentsDisabled"}}')
    )

    with pytest.raises(HttpError):
        fetch_youtube_comments("vid")
