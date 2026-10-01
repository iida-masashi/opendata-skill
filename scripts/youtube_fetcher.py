import argparse
from typing import Any

import polars as pl
from dotenv import load_dotenv
from googleapiclient.discovery import build

from api_utils import cli_entry, require_api_key, save_output

# Load environment variables
load_dotenv()

def fetch_youtube_comments(video_id: str, max_results: int = 100, output_file: str | None = None) -> pl.DataFrame:
    """
    Fetches comments from a YouTube video using YouTube Data API v3.
    Requirement: YOUTUBE_API_KEY in .env

    googleapiclient.errors.HttpError（コメント無効・クォータ超過等）はそのまま送出する。
    """
    api_key = require_api_key("YOUTUBE_API_KEY", "Google Cloud Console", "https://console.cloud.google.com/")

    youtube = build("youtube", "v3", developerKey=api_key)

    print(f"Fetching comments for video ID: {video_id} (Max: {max_results})...")

    comments: list[dict[str, Any]] = []

    # Initial request
    request = youtube.commentThreads().list(
        part="snippet",
        videoId=video_id,
        maxResults=min(max_results, 100), # API limit per page
        textFormat="plainText",
        order="relevance" # or "time"
    )

    while request and len(comments) < max_results:
        response = request.execute()

        for item in response.get("items", []):
            snippet = item["snippet"]["topLevelComment"]["snippet"]
            comments.append({
                "Author": snippet["authorDisplayName"],
                "Text": snippet["textDisplay"],
                "LikeCount": snippet["likeCount"],
                "PublishedAt": snippet["publishedAt"],
                "VideoID": video_id
            })

        # Check for next page
        if "nextPageToken" in response and len(comments) < max_results:
            request = youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=min(max_results - len(comments), 100),
                textFormat="plainText",
                order="relevance",
                pageToken=response["nextPageToken"]
            )
        else:
            break

    if not comments:
        print("No comments found.")
        return pl.DataFrame()

    df = pl.DataFrame(comments)
    save_output(df, output_file)
    return df

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch YouTube Comments.")
    parser.add_argument("video_id", help="YouTube Video ID")
    parser.add_argument("--max", type=int, default=100, help="Max results")
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    fetch_youtube_comments(args.video_id, args.max, args.out or f"youtube_comments_{args.video_id}.csv")

if __name__ == "__main__":
    cli_entry(main)
