import argparse
import json
import os
import urllib.parse
from typing import Any

import polars as pl
import requests  # noqa: F401 - テストが x_grok_fetcher.requests.post を patch する
from dotenv import load_dotenv

from api_utils import cli_entry, default_date_range, post_with_retry, require_api_key, save_output

# Load environment variables
load_dotenv()


def _output_text(data: dict[str, Any]) -> tuple[str, list[str]]:
    """Responses API の応答から (本文テキスト, 引用URL一覧) を取り出す。"""
    texts: list[str] = []
    cited: list[str] = list(data.get("citations") or [])
    for item in data.get("output") or []:
        if item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if part.get("type") == "output_text":
                texts.append(part.get("text") or "")
                cited += [a.get("url") for a in part.get("annotations") or [] if a.get("url")]
    return "".join(texts), cited


def fetch_x_grok(query: str, limit: int = 10, output_file: str | None = None) -> pl.DataFrame:
    """
    Fetches real-time X (Twitter) posts via Grok (xAI) API.
    Requirement: XAI_API_KEY in .env

    This implementation is inspired by the 'grok_context_research.ts' script
    from the HayattiQ/x-research-skills repository.

    X の検索は xAI Responses API (POST /v1/responses) の組み込みツール x_search で行う
    (https://docs.x.ai/developers/tools/x-search)。旧 Chat Completions の Live Search
    (search_parameters) は廃止済みで、ツール無しの chat/completions ではモデルが
    投稿を「生成」してしまう。引用 (citations) が1件も無い応答は実データの裏付けが無いので例外にする。
    """
    api_key = require_api_key("XAI_API_KEY", "xAI Console", "https://console.x.ai/")

    # Use the base URL if provided in env, otherwise default
    base_url = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1/responses")
    model = os.getenv("XAI_MODEL", "grok-4-latest") # Default to grok-4-latest

    print(f"Searching X via Grok for: '{query}' (Limit: {limit}, Model: {model})...")

    # Prompt engineering inspired by "X Research Skills"
    # We ask Grok to act as a research assistant and return structured data.
    # The key is to ask for a JSON list of posts.

    system_prompt = """
    You are an expert researcher. Use the X search tool to find posts for the user's query.
    Only report posts that the X search tool actually returned; never invent posts.

    Return the result strictly as a JSON list of objects.
    Each object must have the following keys:
    - author: The display name or handle of the post author.
    - content: The full text content of the post.
    - date: The publication date/time of the post (YYYY-MM-DD HH:MM:SS format if possible).
    - url: The permalink URL to the post.

    Do not include any conversational text, markdown formatting (like ```json), or explanations.
    Just the raw JSON array. If no posts were found, return [].
    """  # noqa: E501

    from_date, to_date = default_date_range(None, None, 30)
    user_prompt = f"Search query: {query}. Fetch {limit} relevant posts from the last 30 days."  # noqa: E501

    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "tools": [{"type": "x_search", "from_date": from_date, "to_date": to_date}],
        "stream": False,
        "temperature": 0.0 # Deterministic output
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    response = post_with_retry(base_url, headers=headers, json=payload)
    data = response.json()

    content, cited = _output_text(data)
    if not content:
        raise RuntimeError(f"Grok API returned no output_text: {str(data)[:300]}")

    # Clean up markdown code blocks if present
    content = content.replace("```json", "").replace("```", "").strip()

    try:
        posts = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"Grok の応答を JSON として解析できません: {content[:500]}") from e

    if not posts:
        print("No posts found matching criteria.")
        return pl.DataFrame()

    if not cited:
        raise RuntimeError(
            "Grok returned posts but no citation from x_search; refusing to treat them as real posts."
        )

    df = pl.DataFrame(posts, infer_schema_length=None)
    save_output(df, output_file)
    return df

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch X posts via Grok API.")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--limit", type=int, default=10, help="Number of posts to fetch")  # noqa: E501
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    safe_query = urllib.parse.quote(args.query.replace(" ", "_")[:50], safe="")
    fetch_x_grok(args.query, args.limit, args.out or f"x_grok_{safe_query}.csv")

if __name__ == "__main__":
    cli_entry(main)
