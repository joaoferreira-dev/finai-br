from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import feedparser
from pydantic import BaseModel


class NewsItem(BaseModel):
    title: str
    link: str
    published_at: datetime | None = None
    summary: str = ""


def fetch_news(ticker: str) -> list[NewsItem]:
    url = f"https://news.google.com/rss/search?q={quote_plus(ticker + ' ação')}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    feed = feedparser.parse(url)
    limit = datetime.now(timezone.utc) - timedelta(hours=24)
    results = []
    for entry in feed.entries:
        published = parsedate_to_datetime(entry.published) if getattr(entry, "published", None) else None
        if published and published.astimezone(timezone.utc) < limit:
            continue
        results.append(NewsItem(title=entry.get("title", "Sem título"), link=entry.get("link", ""), summary=entry.get("summary", ""), published_at=published))
    return results
