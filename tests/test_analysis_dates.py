"""Analysis days follow the São Paulo run clock, independently of price days."""

import json
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import main
from agents.schemas import TickerAnalysis
from database.models import Analysis, Asset, Base, Price
from delivery import email
from ingestion.market_context import DailyObservation, quotation_from_rows
from settings import Settings


@pytest.fixture
def sessions():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(Asset(ticker="PETR4", name="Petrobras"))
        session.commit()
    yield factory
    engine.dispose()


def test_run_date_reruns_and_next_day_with_unchanged_quote(monkeypatch, sessions):
    clock = {"now": datetime(2026, 9, 24, 0, 30, tzinfo=timezone.utc), "calls": 0}

    class Clock:
        @staticmethod
        def now(tz):
            assert str(tz) == "America/Sao_Paulo"
            clock["calls"] += 1
            return clock["now"].astimezone(tz)

    class Workflow:
        def __init__(self, settings):
            pass

        def invoke(self, ticker, price, news):
            return TickerAnalysis(
                direction="neutro", confidence=0, time_horizon="incerto",
                rationale="Sem evidência relevante.",
            )

    quote = quotation_from_rows([
        DailyObservation(date(2026, 9, 22), 48.35, 48.35, 48_852_400),
    ], "yfinance")
    monkeypatch.setattr(main, "datetime", Clock)
    monkeypatch.setattr(main, "SessionLocal", sessions)
    monkeypatch.setattr(main, "get_settings", lambda: object())
    monkeypatch.setattr(main, "MarketWorkflow", Workflow)
    monkeypatch.setattr(main, "fetch_price", lambda ticker: quote)
    monkeypatch.setattr(main, "fetch_news", lambda ticker: [])

    main.run_daily_cycle()
    quote["close"] = 49
    main.run_daily_cycle()
    with sessions() as session:
        analysis = session.scalars(select(Analysis)).one()
        assert analysis.analysis_date == date(2026, 9, 23)
        assert analysis.price_date == date(2026, 9, 22)
        assert json.loads(analysis.market_context_json)["close"] == 49
        assert json.loads(analysis.analysis_details_json)["run_at"] == "2026-09-23T21:30:00-03:00"

    clock["now"] = datetime(2026, 9, 24, 3, 30, tzinfo=timezone.utc)
    main.run_daily_cycle()
    with sessions() as session:
        assert session.scalars(select(Analysis.analysis_date).order_by(Analysis.analysis_date)).all() == [
            date(2026, 9, 23), date(2026, 9, 24),
        ]
        assert session.scalars(select(Price.trading_date)).all() == [date(2026, 9, 22)]
    assert clock["calls"] == 3  # One clock reading per cycle, shared by all tickers.


@pytest.mark.parametrize("legacy", [False, True])
def test_report_loads_quote_independently_of_run_date(monkeypatch, sessions, legacy):
    quote_date = date(2026, 9, 22)
    run_date = quote_date if legacy else date(2026, 9, 23)
    quote = quotation_from_rows([
        DailyObservation(quote_date, 48.35, 48.35, 48_852_400),
    ], "yfinance")
    with sessions() as session:
        asset = session.scalars(select(Asset)).one()
        session.add(Price(asset_id=asset.id, trading_date=quote_date, close=48.35))
        session.add(Analysis(
            asset_id=asset.id, analysis_date=run_date,
            price_date=None if legacy else quote_date, sentiment="neutro", confidence=0,
            rationale="Sem evidência relevante.", risks_json="[]",
            market_context_json=json.dumps(quote, default=str),
        ))
        session.commit()

    messages = []

    class SMTP:
        def __init__(self, *args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            pass

        def send_message(self, message):
            messages.append(message)

    monkeypatch.setattr(email, "SessionLocal", sessions)
    monkeypatch.setattr(email, "get_settings", lambda: Settings(
        _env_file=None, email_enabled=True, smtp_host="smtp.example.com",
        smtp_username="", email_from="from@example.com", email_to="to@example.com",
    ))
    monkeypatch.setattr(email.smtplib, "SMTP", SMTP)
    email.send_latest_report()
    assert len(messages) == 1
    message = messages[0]
    assert message["Subject"] == f"FinAI-BR | {run_date:%d/%m/%Y}"
    for kind in ("plain", "html"):
        content = message.get_body(preferencelist=(kind,)).get_content()
        assert f"{run_date:%d/%m/%Y}" in content
        assert "Cotação em" in content
        assert "22/09/2026" in content
        assert "PETR4" in content
