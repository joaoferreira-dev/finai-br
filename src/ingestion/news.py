from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import logging
import re
import unicodedata
from urllib.parse import quote_plus

import feedparser
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class NewsItem(BaseModel):
    title: str
    link: str
    published_at: datetime | None = None
    summary: str = ""
    publisher: str = ""
    content_type: str = "rss_excerpt"


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def normalize_text(value: str) -> str:
    """Return comparable plain text from RSS-provided content."""
    parser = _TextExtractor()
    parser.feed(value or "")
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def deduplicate_news(items: list[NewsItem]) -> list[NewsItem]:
    """Keep the first item for each canonical URL or title and publisher."""
    result: list[NewsItem] = []
    seen_links: set[str] = set()
    seen_titles: set[tuple[str, str]] = set()
    for item in items:
        link = item.link.strip().rstrip("/").casefold()
        title_key = (
            unicodedata.normalize("NFKC", normalize_text(item.title)).casefold(),
            unicodedata.normalize("NFKC", normalize_text(item.publisher)).casefold(),
        )
        if (link and link in seen_links) or (title_key[0] and title_key in seen_titles):
            logger.info("Notícia duplicada descartada antes da numeração de fontes")
            continue
        if link:
            seen_links.add(link)
        if title_key[0]:
            seen_titles.add(title_key)
        result.append(item.model_copy(update={"title": normalize_text(item.title), "summary": normalize_text(item.summary), "publisher": normalize_text(item.publisher)}))
    return result


def fetch_news(ticker: str) -> list[NewsItem]:
    url = f"https://news.google.com/rss/search?q={quote_plus(ticker + ' ação')}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    feed = feedparser.parse(url)
    limit = datetime.now(timezone.utc) - timedelta(hours=24)
    results = []
    for entry in feed.entries:
        published = parsedate_to_datetime(entry.published) if getattr(entry, "published", None) else None
        if published and published.astimezone(timezone.utc) < limit:
            continue
        source = entry.get("source", {})
        publisher = source.get("title", "") if isinstance(source, dict) else ""
        results.append(NewsItem(title=entry.get("title", "Sem título"), link=entry.get("link", ""), summary=entry.get("summary", ""), published_at=published, publisher=publisher))
    return deduplicate_news(results)
