"""Tests for x_grok_fetcher.py (xAI Responses API + x_search ツール)."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

import x_grok_fetcher
from x_grok_fetcher import fetch_x_grok


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "dummy")
    monkeypatch.delenv("XAI_BASE_URL", raising=False)


def _responses_body(posts: list[dict], citations: list[str]) -> dict:
    return {
        "output": [
            {"type": "custom_tool_call", "name": "x_keyword_search"},
            {"type": "message", "content": [
                {"type": "output_text", "text": "```json\n" + json.dumps(posts) + "\n```",
                 "annotations": [{"type": "url_citation", "url": u} for u in citations]},
            ]},
        ],
        "citations": citations,
    }


POST = {"author": "a", "content": "hello", "date": "2024-01-01 00:00:00", "url": "https://x.com/a/status/1"}


@patch("x_grok_fetcher.requests.post")
def test_request_enables_x_search_tool(mock_post: MagicMock, make_response) -> None:
    """検索ツール無しの chat/completions では投稿をモデルが生成してしまう。"""
    mock_post.return_value = make_response(json=_responses_body([POST], [POST["url"]]))

    df = fetch_x_grok("xAI", limit=5)

    url = mock_post.call_args[0][0]
    payload = mock_post.call_args[1]["json"]
    assert url.endswith("/v1/responses")
    tools = payload["tools"]
    assert tools[0]["type"] == "x_search"
    assert len(tools[0]["from_date"]) == 10 and len(tools[0]["to_date"]) == 10  # YYYY-MM-DD
    assert df["url"].to_list() == [POST["url"]]


@patch("x_grok_fetcher.requests.post")
def test_posts_without_any_citation_raise(mock_post: MagicMock, make_response) -> None:
    """検索結果（citations）が無いのに投稿が返った = 実データの裏付けが無い。"""
    mock_post.return_value = make_response(json=_responses_body([POST], []))

    with pytest.raises(RuntimeError, match="citation"):
        fetch_x_grok("xAI")


@patch("x_grok_fetcher.requests.post")
def test_keys_beyond_first_100_posts_are_kept(mock_post: MagicMock, make_response) -> None:
    posts = [dict(POST) for _ in range(100)] + [{**POST, "likes": 3}]
    mock_post.return_value = make_response(json=_responses_body(posts, [POST["url"]]))

    df = fetch_x_grok("xAI", limit=101)

    assert df["likes"].to_list()[-1] == 3


@patch("x_grok_fetcher.requests.post")
def test_unparseable_output_raises(mock_post: MagicMock, make_response) -> None:
    body = _responses_body([], [POST["url"]])
    body["output"][1]["content"][0]["text"] = "Sorry, I could not find posts."
    mock_post.return_value = make_response(json=body)

    with pytest.raises(ValueError):
        fetch_x_grok("xAI")


@patch("x_grok_fetcher.requests.post")
def test_http_error_raises(mock_post: MagicMock, make_response) -> None:
    mock_post.return_value = make_response(status=401, text='{"error":"bad key"}')

    with pytest.raises(requests.exceptions.HTTPError):
        fetch_x_grok("xAI")


@patch("x_grok_fetcher.requests.post")
def test_cli_default_filename_escapes_slash(
    mock_post: MagicMock, make_response, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    mock_post.return_value = make_response(json=_responses_body([POST], [POST["url"]]))
    monkeypatch.setattr("sys.argv", ["x_grok_fetcher.py", "AI/ML news"])

    x_grok_fetcher.main()

    files = list(tmp_path.iterdir())
    assert len(files) == 1
    assert files[0].name.startswith("x_grok_")
