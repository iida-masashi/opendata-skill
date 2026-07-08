import argparse
import json
import os

import polars as pl
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def fetch_x_grok(query: str, limit: int = 10, output_file: str | None = None) -> None:
    """
    Fetches real-time X (Twitter) posts via Grok (xAI) API.
    Requirement: XAI_API_KEY in .env
    
    This implementation is inspired by the 'grok_context_research.ts' script
    from the HayattiQ/x-research-skills repository.
    It uses the 'grok-beta' (or similar) model to perform a search and 
    retrieve relevant posts.
    """  # noqa: W291, W293

    try:
        from api_utils import require_api_key
    except ImportError:
        from .api_utils import require_api_key

    api_key = require_api_key("XAI_API_KEY", "xAI Console", "https://console.x.ai/")

    # Use the base URL if provided in env, otherwise default
    base_url = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1/chat/completions")
    model = os.getenv("XAI_MODEL", "grok-4-latest") # Default to grok-4-latest

    print(f"Searching X via Grok for: '{query}' (Limit: {limit}, Model: {model})...")

    # Prompt engineering inspired by "X Research Skills"
    # We ask Grok to act as a research assistant and return structured data.
    # The key is to ask for a JSON list of posts.

    system_prompt = """
    You are an expert researcher with access to real-time X (Twitter) data.
    Your task is to search for the user's query and extract the most relevant and recent posts.
    
    Return the result strictly as a JSON list of objects.
    Each object must have the following keys:
    - author: The display name or handle of the post author.
    - content: The full text content of the post.
    - date: The publication date/time of the post (YYYY-MM-DD HH:MM:SS format if possible).
    - url: The permalink URL to the post.
    
    Do not include any conversational text, markdown formatting (like ```json), or explanations.
    Just the raw JSON array.
    """  # noqa: E501, W293

    user_prompt = f"Search query: {query}. Fetch {limit} relevant posts from the last 30 days."  # noqa: E501

    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "model": model,
        "stream": False,
        "temperature": 0.0 # Deterministic output
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    try:
        response = requests.post(base_url, headers=headers, json=payload)  # noqa: S113
        response.raise_for_status()
        data = response.json()

        # Check if choices exist
        if "choices" not in data or not data["choices"]:
            print("Error: No choices returned from Grok API.")
            return

        content = data["choices"][0]["message"]["content"]

        # Clean up markdown code blocks if present
        content = content.replace("```json", "").replace("```", "").strip()

        # Parse JSON
        try:
            posts = json.loads(content)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON response: {e}")
            print("Raw content received:")
            print(content[:500] + "...") # Print first 500 chars
            return

    except Exception as e:  # noqa: BLE001
        print(f"Error communicating with Grok API: {e}")
        return

    if not posts:
        print("No posts found matching criteria.")
        return

    df = pl.DataFrame(posts)

    if not output_file:
        safe_query = query.replace(" ", "_")[:50]
        output_file = f"x_grok_{safe_query}.csv"

    print(f"Saving {len(df)} posts to {output_file}...")
    try:
        df.write_csv(output_file, include_header=True)
    except Exception as e:  # noqa: BLE001
        print(f"Error saving CSV: {e}")

    print("Done.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch X posts via Grok API.")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--limit", type=int, default=10, help="Number of posts to fetch")  # noqa: E501
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    fetch_x_grok(args.query, args.limit, args.out)
