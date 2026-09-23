import json
from datetime import date
from types import SimpleNamespace

import pandas as pd

from delivery.report import render_html, render_text, report_items_from_rows
from ingestion.market_context import DailyObservation, quotation_from_rows


def test_report_uses_saved_context_and_shows_exact_window_dates() -> None:
    days = pd.bdate_range(start="2026-07-01", periods=31)
    rows = [DailyObservation(day.date(), 100 + index, 50 + index, 1000 + index) for index, day in enumerate(days)]
    quotation = quotation_from_rows(rows, "yfinance")
    saved = {**quotation, "trading_date": quotation["trading_date"].isoformat()}
    analysis = SimpleNamespace(
        analysis_date=quotation["trading_date"], direction="neutro", sentiment="neutro",
        time_horizon="incerto", confidence=30, rationale="Dados [1].", risks_json="[]",
        sources=[], market_context_json=json.dumps(saved),
    )
    row = SimpleNamespace(
        Analysis=analysis, Asset=SimpleNamespace(ticker="PETR4"),
        Price=SimpleNamespace(close=1, change_percent=None, volume=None),
    )
    item = report_items_from_rows([row])[0]
    assert item.close == quotation["close"]
    text = render_text([item])
    html = render_html([item])
    assert "Variação ajustada em 5 pregões:" in text
    assert "Variação ajustada em 30 pregões:" in text
    assert "Volume vs. média dos 20 pregões anteriores:" in text
    assert item.historical_context.change_5_sessions.start_date.strftime("%d/%m/%Y") in text
    assert "1,01×" in text
    assert item.historical_context.average_volume_20_sessions.end_date.strftime("%d/%m/%Y") in text
    assert "Variação ajustada em 5 pregões" in html
    assert "1,01×" in html


def test_legacy_and_missing_metrics_render_without_invented_numbers() -> None:
    legacy = SimpleNamespace(
        Analysis=SimpleNamespace(analysis_date=date(2026, 9, 18), direction="neutro", sentiment="neutro",
                                 time_horizon="incerto", confidence=30, rationale="Sem dados.", risks_json="[]", sources=[]),
        Asset=SimpleNamespace(ticker="PETR4"),
        Price=SimpleNamespace(close=42, change_percent=None, volume=None),
    )
    item = report_items_from_rows([legacy])[0]
    assert "Histórico: indisponível" in render_text([item])
    assert "(indisponível)" in render_text([item])
    legacy_html = render_html([item])
    assert "Histórico" in legacy_html
    assert '<strong class="">indisponível</strong>' in legacy_html


def test_partial_context_shows_unavailable_metrics_in_both_formats() -> None:
    quotation = quotation_from_rows([DailyObservation(date(2026, 9, 18), 42, None, None)], "brapi")
    saved = {**quotation, "trading_date": quotation["trading_date"].isoformat()}
    analysis = SimpleNamespace(
        analysis_date=date(2026, 9, 18), direction="neutro", sentiment="neutro",
        time_horizon="incerto", confidence=20, rationale="Sem notícia suficiente.",
        risks_json="[]", sources=[], market_context_json=json.dumps(saved),
    )
    row = SimpleNamespace(
        Analysis=analysis, Asset=SimpleNamespace(ticker="PETR4"),
        Price=SimpleNamespace(close=42, change_percent=None, volume=None),
    )
    item = report_items_from_rows([row])[0]
    text = render_text([item])
    html = render_html([item])
    assert text.count("indisponível (histórico insuficiente)") == 3
    assert "(indisponível)" in text
    assert html.count("indisponível (histórico insuficiente)") == 3
