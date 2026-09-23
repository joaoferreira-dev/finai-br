from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from ingestion import market_data, news
from ingestion.news import NewsItem, deduplicate_news


def test_fetch_news_keeps_recent_entries_and_discards_old_entries(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    class FeedEntry(dict):
        __getattr__ = dict.get

    feed = type("Feed", (), {
        "entries": [
            FeedEntry({
                "title": "Noticia recente",
                "link": "https://example.com/recent",
                "summary": "Resumo",
                "published": (now - timedelta(hours=2)).strftime("%a, %d %b %Y %H:%M:%S GMT"),
            }),
            FeedEntry({
                "title": "Noticia antiga",
                "link": "https://example.com/old",
                "published": (now - timedelta(hours=25)).strftime("%a, %d %b %Y %H:%M:%S GMT"),
            }),
            FeedEntry({"link": "https://example.com/undated"}),
        ]
    })()
    monkeypatch.setattr(news.feedparser, "parse", lambda url: feed)

    results = news.fetch_news("PETR4")

    assert [item.title for item in results] == ["Noticia recente", "Sem título"]
    assert results[1].published_at is None


def test_fetch_news_strips_html_and_extracts_rss_publisher(monkeypatch) -> None:
    feed = type("Feed", (), {"entries": [{
        "title": "PETR4 em alta",
        "link": "https://example.com/story",
        "summary": "<p>Caixa <b>forte</b>&nbsp;e dívida menor</p>",
        "source": {"title": "Jornal Exemplo"},
    }]})()
    monkeypatch.setattr(news.feedparser, "parse", lambda url: feed)

    item = news.fetch_news("PETR4")[0]

    assert item.summary == "Caixa forte e dívida menor"
    assert item.publisher == "Jornal Exemplo"
    assert item.content_type == "rss_excerpt"


def test_news_deduplication_preserves_first_item_and_stable_order() -> None:
    items = [
        NewsItem(title="PETR4 <b>subiu</b>", publisher="Jornal", link="https://example.com/a", summary="Um"),
        NewsItem(title="PETR4 subiu", publisher="Jornal", link="https://example.com/b", summary="Dois"),
        NewsItem(title="Outra notícia", publisher="Jornal", link="https://example.com/a/", summary="Três"),
        NewsItem(title="Outra notícia", publisher="Jornal B", link="https://example.com/c", summary="Quatro"),
    ]

    result = deduplicate_news(items)

    assert [item.summary for item in result] == ["Um", "Quatro"]


def test_fetch_price_calculates_change_from_previous_close(monkeypatch) -> None:
    history = pd.DataFrame(
        {"Close": [100.0, 110.0], "Adj Close": [98.0, 108.0], "Volume": [1000, 2500]},
        index=pd.to_datetime(["2026-09-15", "2026-09-16"]),
    )

    class FakeTicker:
        def history(self, **kwargs):
            assert kwargs == {"period": "3mo", "interval": "1d", "auto_adjust": False}
            return history

    monkeypatch.setattr(market_data.yf, "Ticker", lambda ticker: FakeTicker())

    result = market_data.fetch_price("PETR4")

    assert result["trading_date"] == datetime(2026, 9, 16).date()
    assert result["close"] == 110.0
    assert result["change_percent"] == pytest.approx(10.0)
    assert result["volume"] == 2500
    assert result["historical_context"]["change_5_sessions"]["value"] is None


def test_fetch_price_raises_when_history_is_empty(monkeypatch) -> None:
    class FakeTicker:
        def history(self, **kwargs):
            return pd.DataFrame()

    monkeypatch.setattr(market_data.yf, "Ticker", lambda ticker: FakeTicker())
    monkeypatch.setattr(market_data, "_fetch_price_brapi", lambda ticker: (_ for _ in ()).throw(RuntimeError("Brapi indisponível")))

    try:
        market_data.fetch_price("PETR4")
    except RuntimeError as error:
        assert str(error) == "Não foi possível obter cotação de PETR4 via yfinance ou Brapi"
    else:
        raise AssertionError("fetch_price deveria falhar sem cotações")


def test_fetch_price_uses_brapi_when_yfinance_is_rate_limited(monkeypatch) -> None:
    monkeypatch.setattr(market_data, "_fetch_price_yfinance", lambda ticker: (_ for _ in ()).throw(RuntimeError("Too Many Requests")))
    fallback = {
        "trading_date": datetime(2026, 9, 16).date(),
        "close": 35.2,
        "change_percent": 1.5,
        "volume": 1000,
    }
    monkeypatch.setattr(market_data, "_fetch_price_brapi", lambda ticker: fallback)

    assert market_data.fetch_price("PETR4") == fallback


def test_fetch_price_retries_yfinance_for_each_ticker(monkeypatch) -> None:
    attempted = []
    fallback = {
        "trading_date": datetime(2026, 9, 16).date(),
        "close": 35.2,
        "change_percent": 1.5,
        "volume": 1000,
    }

    def fail_yfinance(ticker):
        attempted.append(ticker)
        raise RuntimeError("rate limited")

    monkeypatch.setattr(market_data, "_fetch_price_yfinance", fail_yfinance)
    monkeypatch.setattr(market_data, "_fetch_price_brapi", lambda ticker: fallback)

    market_data.fetch_price("PETR4")
    market_data.fetch_price("BBAS3")

    assert attempted == ["PETR4", "BBAS3"]
