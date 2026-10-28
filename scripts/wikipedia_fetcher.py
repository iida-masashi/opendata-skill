import argparse
from collections.abc import Sequence
from urllib.parse import quote

import polars as pl
import requests
from api_utils import cli_entry, default_date_range, get_with_retry, save_output

BASE_URL = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
DEFAULT_HEADERS = {
    "User-Agent": "OpenDataSkill/2.4 (https://github.com/iida-masashi/opendata-skill; demand-forecasting-toolkit)",
    "Accept": "application/json",
}


def _normalize_project(lang_or_project: str) -> str:
    """'ja' -> 'ja.wikipedia', 'en.wikipedia.org' -> 'en.wikipedia' に正規化する。"""
    s = lang_or_project.strip().lower()
    if s.endswith(".org"):
        s = s[:-4]
    if "." not in s:
        return f"{s}.wikipedia"
    return s


def _format_wiki_timestamp(date_str: str) -> str:
    """'YYYY-MM-DD' または 'YYYYMMDD' を Wikimedia API 形式 'YYYYMMDD00' に変換する。"""
    clean = date_str.strip().replace("-", "").replace("/", "")
    if len(clean) == 8 and clean.isdigit():
        return f"{clean}00"
    if len(clean) == 10 and clean.isdigit():
        return clean
    raise ValueError(f"Invalid date format for Wikipedia Pageviews: {date_str} (expected YYYY-MM-DD)")


def _parse_wiki_timestamp(ts: str) -> str:
    """Wikimedia API の timestamp ('YYYYMMDD00') を 'YYYY-MM-DD' に変換する。"""
    if len(ts) >= 8 and ts[:8].isdigit():
        return f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
    return ts


def fetch_wikipedia_pageviews(
    articles: str | Sequence[str],
    lang: str = "ja",
    granularity: str = "daily",
    access: str = "all-access",
    agent: str = "user",
    start_date: str | None = None,
    end_date: str | None = None,
    output_file: str | None = None,
) -> pl.DataFrame:
    """
    Wikimedia REST API から Wikipedia 記事の日次・月次ページビュー数（検索・関心度の先行指標）を取得する。
    APIキー不要・完全無料。

    Parameters
    ----------
    articles : str | Sequence[str]
        記事タイトル（カンマ区切り文字列、または文字列リスト。例: "インフルエンザ,花粉症"）
    lang : str
        言語コードまたはプロジェクト名（デフォルト: 'ja' -> 'ja.wikipedia'）
    granularity : str
        'daily' または 'monthly'
    access : str
        'all-access', 'desktop', 'mobile-app', 'mobile-web'
    agent : str
        'user'（人間のみ、Bot除外推奨）, 'all-agents', 'spider', 'automated'
    start_date : str | None
        開始日 (YYYY-MM-DD)。省略時は365日前。
    end_date : str | None
        終了日 (YYYY-MM-DD)。省略時は今日。
    output_file : str | None
        保存先CSVパス。
    """
    if granularity not in ("daily", "monthly"):
        raise ValueError(f"Unsupported granularity: {granularity}. Choose 'daily' or 'monthly'.")

    if isinstance(articles, str):
        article_list = [a.strip() for a in articles.split(",") if a.strip()]
    else:
        article_list = [str(a).strip() for a in articles if str(a).strip()]

    if not article_list:
        raise ValueError("At least one Wikipedia article title must be specified.")

    start_date, end_date = default_date_range(start_date, end_date, 365)
    start_ts = _format_wiki_timestamp(start_date)
    end_ts = _format_wiki_timestamp(end_date)
    project = _normalize_project(lang)

    records: list[dict[str, object]] = []
    for article in article_list:
        normalized_title = article.replace(" ", "_")
        encoded_title = quote(normalized_title, safe="")
        url = f"{BASE_URL}/{project}/{access}/{agent}/{encoded_title}/{granularity}/{start_ts}/{end_ts}"
        print(f"Fetching Wikipedia pageviews: {article} ({project}, {granularity}, {start_date}->{end_date})...")
        try:
            resp = get_with_retry(url, headers=DEFAULT_HEADERS)
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                print(f"No Wikipedia pageviews found for article '{article}' (HTTP 404).")
                continue
            raise

        data = resp.json()
        items = data.get("items", []) if isinstance(data, dict) else []
        for item in items:
            ts = str(item.get("timestamp", ""))
            views = item.get("views")
            if ts and views is not None:
                records.append({
                    "date": _parse_wiki_timestamp(ts),
                    "article": str(item.get("article", normalized_title)).replace("_", " "),
                    "value": float(views),
                    "project": str(item.get("project", project)),
                })

    if not records:
        print("No Wikipedia pageview records found.")
        return pl.DataFrame()

    df = pl.DataFrame(records).with_columns(pl.col("value").cast(pl.Float64))
    save_output(df, output_file)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch Wikipedia article pageviews from Wikimedia REST API (No API key required)."
    )
    parser.add_argument(
        "--article",
        required=True,
        help="Article title(s), comma-separated (e.g. 'インフルエンザ,花粉症' or 'Nintendo_Switch').",
    )
    parser.add_argument("--lang", default="ja", help="Language code or project (default: ja).")
    parser.add_argument(
        "--granularity",
        default="daily",
        choices=["daily", "monthly"],
        help="Aggregation granularity (default: daily).",
    )
    parser.add_argument("--start", help="Start date (YYYY-MM-DD).")
    parser.add_argument("--end", help="End date (YYYY-MM-DD).")
    parser.add_argument("--out", help="Output CSV filename.")
    args = parser.parse_args()

    fetch_wikipedia_pageviews(
        articles=args.article,
        lang=args.lang,
        granularity=args.granularity,
        start_date=args.start,
        end_date=args.end,
        output_file=args.out,
    )


if __name__ == "__main__":
    cli_entry(main)
