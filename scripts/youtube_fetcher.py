import argparse
from typing import Any

import polars as pl
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Load environment variables
load_dotenv()

def fetch_youtube_comments(video_id: str, max_results: int = 100, output_file: str | None = None) -> None:
    """
    Fetches comments from a YouTube video using YouTube Data API v3.
    Requirement: YOUTUBE_API_KEY in .env
    """

    try:
        from api_utils import require_api_key
    except ImportError:
        from .api_utils import require_api_key

    api_key = require_api_key("YOUTUBE_API_KEY", "Google Cloud Console", "https://console.cloud.google.com/")

    youtube = build("youtube", "v3", developerKey=api_key)

    print(f"Fetching comments for video ID: {video_id} (Max: {max_results})...")

    comments: list[dict[str, Any]] = []

    try:
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

    except HttpError as e:
        print(f"An HTTP error fetched from YouTube API: {e}")
        return

    if not comments:
        print("No comments found.")
        return

    df = pl.DataFrame(comments)

    if not output_file:
        output_file = f"youtube_comments_{video_id}.csv"

    print(f"Saving {len(df)} comments to {output_file}...")
    df.write_csv(output_file, include_header=True)
    print("Done.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch YouTube Comments.")
    parser.add_argument("video_id", help="YouTube Video ID")
    parser.add_argument("--max", type=int, default=100, help="Max results")
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()
    fetch_youtube_comments(args.video_id, args.max, args.out)
