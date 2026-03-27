"""
tools/news.py
Fetch financial news headlines via NewsAPI.
Returns plain data — no reasoning, no formatting.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from newsapi import NewsApiClient

load_dotenv()

CACHE_DIR = Path(__file__).parent.parent / "data"
CACHE_DIR.mkdir(exist_ok=True)


def fetch_headlines(topic: str, days: int = 15) -> list[dict]:
    """
    Fetch news headlines related to a topic over the last `days` days.

    Returns a list of articles, each with:
        title, description, source, url, publishedAt
    """
    cache_file = CACHE_DIR / f"news_{topic.replace(' ', '_')}_{days}d.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    client = NewsApiClient(api_key=os.getenv("NEWSAPI_KEY"))
    from_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    response = client.get_everything(
        q=topic,
        from_param=from_date,
        language="en",
        sort_by="relevancy",
        page_size=100,
    )

    articles = [
        {
            "title": a["title"],
            "description": a.get("description", ""),
            "source": a["source"]["name"],
            "url": a["url"],
            "publishedAt": a["publishedAt"],
        }
        for a in response.get("articles", [])
        if a.get("title") and "[Removed]" not in a.get("title", "")
    ]

    cache_file.write_text(json.dumps(articles, indent=2))
    return articles


def fetch_top_financial_headlines(days: int = 15) -> list[dict]:
    """
    Fetch broad financial/markets headlines without a specific topic.
    Used during auto-discovery mode to identify trending themes.
    """
    cache_file = CACHE_DIR / f"news_financial_broad_{days}d.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    client = NewsApiClient(api_key=os.getenv("NEWSAPI_KEY"))
    from_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    response = client.get_everything(
        q="stock market OR earnings OR federal reserve OR inflation OR sector",
        from_param=from_date,
        language="en",
        sort_by="popularity",
        page_size=100,
    )

    articles = [
        {
            "title": a["title"],
            "description": a.get("description", ""),
            "source": a["source"]["name"],
            "url": a["url"],
            "publishedAt": a["publishedAt"],
        }
        for a in response.get("articles", [])
        if a.get("title") and "[Removed]" not in a.get("title", "")
    ]

    cache_file.write_text(json.dumps(articles, indent=2))
    return articles
