"""Tests for wikipedia_fetcher.py (APIキー不要・モック中心)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from wikipedia_fetcher import (
    _format_wiki_timestamp,
    _normalize_project,
    fetch_wikipedia_pageviews,
)


def test_normalize_project() -> None:
    assert _normalize_project("ja") == "ja.wikipedia"
    assert _normalize_project("en.wikipedia.org") == "en.wikipedia"
    assert _normalize_project("de.wikipedia") == "de.wikipedia"


def test_format_wiki_timestamp() -> None:
    assert _format_wiki_timestamp("2025-01-15") == "2025011500"
    assert _format_wiki_timestamp("20250115") == "2025011500"
    with pytest.raises(ValueError, match="Invalid date format"):
        _format_wiki_timestamp("2025-1-5")


@patch("wikipedia_fetcher.requests.get")
def test_fetch_wikipedia_single_article(mock_get: MagicMock, make_response, tmp_path: Path) -> None:
    mock_get.return_value = make_response(
        json={
            "items": [
                {
                    "project": "ja.wikipedia",
                    "article": "インフルエンザ",
                    "granularity": "daily",
                    "timestamp": "2025010100",
                    "access": "all-access",
                    "agent": "user",
                    "views": 12500,
                },
                {
                    "project": "ja.wikipedia",
                    "article": "インフルエンザ",
                    "granularity": "daily",
                    "timestamp": "2025010200",
                    "access": "all-access",
                    "agent": "user",
                    "views": 14300,
                },
            ]
        }
    )

    out = str(tmp_path / "wiki.csv")
    df = fetch_wikipedia_pageviews(
        articles="インフルエンザ",
        lang="ja",
        start_date="2025-01-01",
        end_date="2025-01-02",
        output_file=out,
    )
    assert df.height == 2
    assert set(df.columns) == {"date", "article", "value", "project"}
    assert df.get_column("date").to_list() == ["2025-01-01", "2025-01-02"]
    assert df.get_column("value").to_list() == [12500.0, 14300.0]
    assert Path(out).exists()
    # URLに日本語タイトルがURLエンコードされて含まれること
    called_url = mock_get.call_args[0][0]
    assert "%E3%82%A4%E3%83%B3%E3%83%95%E3%83%AB%E3%82%A8%E3%83%B3%E3%82%B6" in called_url


@patch("wikipedia_fetcher.requests.get")
def test_fetch_wikipedia_multiple_articles_with_404_skip(mock_get: MagicMock, make_response) -> None:
    """複数記事指定時、存在しない記事(404)はスキップし、取得できた記事のみ返す。"""
    resp_ok = make_response(
        json={
            "items": [
                {
                    "project": "ja.wikipedia",
                    "article": "花粉症",
                    "timestamp": "2025030100",
                    "views": 8900,
                }
            ]
        }
    )
    resp_404 = make_response(json={"detail": "Not found"}, status=404)
    mock_get.side_effect = [resp_404, resp_ok]

    df = fetch_wikipedia_pageviews(
        articles=["存在しない記事XYZ", "花粉症"],
        lang="ja",
        start_date="2025-03-01",
        end_date="2025-03-01",
    )
    assert df.height == 1
    assert df.get_column("article").to_list() == ["花粉症"]
    assert df.get_column("value").to_list() == [8900.0]


def test_invalid_granularity_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported granularity"):
        fetch_wikipedia_pageviews("花粉症", granularity="hourly")


def test_empty_articles_raises() -> None:
    with pytest.raises(ValueError, match="At least one"):
        fetch_wikipedia_pageviews(" , ")
