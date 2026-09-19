import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import yfinance as yf

from settings import get_settings

logger = logging.getLogger(__name__)
_yfinance_disabled = False


def _format_price(latest: dict, previous: dict) -> dict:
    close = float(latest["close"])
    old_close = float(previous["close"])
    return {
        "trading_date": latest["trading_date"],
        "close": close,
        "change_percent": ((close / old_close) - 1) * 100 if old_close else 0.0,
        "volume": int(latest.get("volume") or 0),
    }


def _fetch_price_yfinance(ticker: str) -> dict:
    history = yf.Ticker(f"{ticker}.SA").history(period="5d", auto_adjust=False)
    if history.empty:
        raise RuntimeError("yfinance não retornou cotações")
    latest = history.iloc[-1]
    previous = history.iloc[-2] if len(history) > 1 else latest
    latest_values = {"trading_date": latest.name.date(), "close": latest["Close"], "volume": latest["Volume"]}
    previous_values = {"trading_date": previous.name.date(), "close": previous["Close"], "volume": previous["Volume"]}
    return _format_price(latest_values, previous_values)


def _fetch_price_brapi(ticker: str) -> dict:
    settings = get_settings()
    query = {"range": "5d", "interval": "1d"}
    if settings.brapi_token:
        query["token"] = settings.brapi_token
    request = Request(f"https://brapi.dev/api/quote/{ticker}?{urlencode(query)}")
    with urlopen(request, timeout=15) as response:
        payload = json.load(response)
    history = [
        item for item in payload.get("results", [{}])[0].get("historicalDataPrice", [])
        if item.get("close") is not None and item.get("date") is not None
    ]
    if not history:
        raise RuntimeError("Brapi não retornou cotações")
    history.sort(key=lambda item: item["date"])
    latest, previous = history[-1], history[-2] if len(history) > 1 else history[-1]
    latest_values = {
        "trading_date": datetime.fromtimestamp(latest["date"], timezone.utc).date(),
        "close": latest["close"],
        "volume": latest.get("volume"),
    }
    previous_values = {"close": previous["close"], "volume": previous.get("volume")}
    return _format_price(latest_values, previous_values)


def fetch_price(ticker: str) -> dict:
    global _yfinance_disabled
    if not _yfinance_disabled:
        try:
            return _fetch_price_yfinance(ticker)
        except Exception as yfinance_error:
            _yfinance_disabled = True
            logger.warning("yfinance falhou para %s; usando Brapi para o restante do ciclo: %s", ticker, yfinance_error)
    try:
        return _fetch_price_brapi(ticker)
    except Exception as brapi_error:
        raise RuntimeError(f"Não foi possível obter cotação de {ticker} via yfinance ou Brapi") from brapi_error
