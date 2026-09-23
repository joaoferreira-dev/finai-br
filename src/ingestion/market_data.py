"""Collect and normalize daily B3 quotations from yfinance or Brapi."""

import json
import logging
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import yfinance as yf

from ingestion.market_context import DailyObservation, nonnegative_volume, positive_price, quotation_from_rows
from settings import get_settings

logger = logging.getLogger(__name__)


def _fetch_price_yfinance(ticker: str) -> dict:
    history = yf.Ticker(f"{ticker}.SA").history(period="3mo", interval="1d", auto_adjust=False)
    if history.empty:
        raise RuntimeError("yfinance não retornou cotações")
    observations = [
        DailyObservation(
            trading_date=day.date(),
            close=positive_price(row.get("Close")),
            adjusted_close=positive_price(row.get("Adj Close")),
            volume=nonnegative_volume(row.get("Volume")),
        )
        for day, row in history.iterrows()
    ]
    return quotation_from_rows(observations, "yfinance")


def _fetch_price_brapi(ticker: str) -> dict:
    settings = get_settings()

    def load_history(period: str) -> list[dict]:
        query = {"range": period, "interval": "1d"}
        if settings.brapi_token:
            query["token"] = settings.brapi_token
        request = Request(f"https://brapi.dev/api/quote/{ticker}?{urlencode(query)}")
        with urlopen(request, timeout=15) as response:
            payload = json.load(response)
        return payload.get("results", [{}])[0].get("historicalDataPrice", [])

    try:
        history = load_history("3mo")
    except HTTPError as error:
        if error.code not in {400, 403}:
            raise
        logger.warning("Brapi rejeitou o histórico de 3 meses para %s; tentando 5 dias", ticker)
        history = load_history("5d")
    if not history:
        raise RuntimeError("Brapi não retornou cotações")
    observations = [
        DailyObservation(
            trading_date=datetime.fromtimestamp(item["date"], timezone.utc).date(),
            close=positive_price(item.get("close")),
            adjusted_close=positive_price(item.get("adjustedClose")),
            volume=nonnegative_volume(item.get("volume")),
        )
        for item in history if item.get("date") is not None
    ]
    return quotation_from_rows(observations, "brapi")


def fetch_price(ticker: str) -> dict:
    try:
        return _fetch_price_yfinance(ticker)
    except Exception as yfinance_error:
        logger.warning("yfinance falhou para %s; usando Brapi para este ativo: %s", ticker, yfinance_error)
    try:
        return _fetch_price_brapi(ticker)
    except Exception as brapi_error:
        raise RuntimeError(f"Não foi possível obter cotação de {ticker} via yfinance ou Brapi") from brapi_error
