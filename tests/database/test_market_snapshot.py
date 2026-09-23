import json
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import main
from agents.schemas import Direction, TickerAnalysis, TimeHorizon
from database.models import Analysis, Asset, Base, Price
from database import session as database_session
from ingestion.market_context import DailyObservation, quotation_from_rows


def test_nullable_quotation_fields_can_be_persisted() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        asset = Asset(ticker="PETR4", name="Petrobras")
        session.add(asset)
        session.flush()
        session.add(Price(asset_id=asset.id, trading_date=date(2026, 9, 18), close=42, change_percent=None, volume=None))
        session.commit()
        price = session.query(Price).one()
        assert price.change_percent is None
        assert price.volume is None


def test_bootstrap_statements_can_be_repeated(monkeypatch) -> None:
    statements = []

    class FakeConnection:
        def execute(self, statement):
            statements.append(str(statement))

    class FakeEngine:
        def begin(self):
            class Context:
                def __enter__(self):
                    return FakeConnection()

                def __exit__(self, *args):
                    return False

            return Context()

    monkeypatch.setattr(database_session, "engine", FakeEngine())
    database_session._ensure_analysis_columns()
    database_session._ensure_analysis_columns()
    assert len(statements) == 16
    assert statements.count("ALTER TABLE analyses ADD COLUMN IF NOT EXISTS price_date DATE") == 2
    assert statements.count("ALTER TABLE analyses ADD COLUMN IF NOT EXISTS market_context_json TEXT") == 2
    assert statements.count("ALTER TABLE analyses ADD COLUMN IF NOT EXISTS analysis_details_json TEXT") == 2
    assert statements.count("ALTER TABLE news ADD COLUMN IF NOT EXISTS publisher VARCHAR(255)") == 2
    assert statements.count("ALTER TABLE prices ALTER COLUMN volume DROP NOT NULL") == 2


def test_daily_cycle_persists_and_replaces_snapshot(monkeypatch) -> None:
    asset = Asset(id=1, ticker="PETR4", name="Petrobras")
    state = {"price": None, "analysis": None, "commits": 0}
    quotation = quotation_from_rows([
        DailyObservation(date(2026, 9, 17), 40, 39, 100),
        DailyObservation(date(2026, 9, 18), 42, 41, None),
    ], "yfinance")

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def scalars(self, query):
            return type("Rows", (), {"all": lambda self: [asset]})()

        def scalar(self, query):
            entity = query.column_descriptions[0]["entity"]
            if entity is Price:
                return state["price"]
            if entity is Analysis:
                return state["analysis"]
            return None

        def add(self, item):
            if isinstance(item, Price):
                state["price"] = item
            elif isinstance(item, Analysis):
                state["analysis"] = item

        def flush(self):
            return None

        def commit(self):
            state["commits"] += 1

    class FakeWorkflow:
        def __init__(self, settings):
            pass

        def invoke(self, ticker, price, news):
            return TickerAnalysis(
                direction=Direction.NEUTRAL, confidence=30,
                time_horizon=TimeHorizon.UNCERTAIN, rationale="Dados limitados.",
            )

    monkeypatch.setattr(main, "SessionLocal", FakeSession)
    monkeypatch.setattr(main, "MarketWorkflow", FakeWorkflow)
    monkeypatch.setattr(main, "get_settings", lambda: object())
    monkeypatch.setattr(main, "fetch_price", lambda ticker: quotation)
    monkeypatch.setattr(main, "fetch_news", lambda ticker: [])

    main.run_daily_cycle()
    first_snapshot = json.loads(state["analysis"].market_context_json)
    first_details = json.loads(state["analysis"].analysis_details_json)
    assert first_details["version"] == 1
    assert first_details["analysis"]["confidence"] == 30
    assert first_snapshot["historical_context"]["as_of_date"] == "2026-09-18"
    assert state["price"].volume is None
    assert state["price"].change_percent == pytest.approx(5)

    quotation = {**quotation, "historical_context": {**quotation["historical_context"], "provider": "brapi"}}
    main.run_daily_cycle()
    second_snapshot = json.loads(state["analysis"].market_context_json)
    assert second_snapshot["historical_context"]["provider"] == "brapi"
    assert state["commits"] == 2
