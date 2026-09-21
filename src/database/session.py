from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from database.models import Asset, Base
from settings import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

DEFAULT_ASSETS = {
    "PETR4": "Petrobras PN",
    "BBAS3": "Banco do Brasil ON",
    "VALE3": "Vale ON",
    "ITUB4": "Itaú Unibanco PN",
    "CSMG3": "Copasa ON",
}


def initialise_database() -> None:
    Base.metadata.create_all(engine)
    _ensure_analysis_columns()
    with SessionLocal() as session:
        existing = {ticker for ticker, in session.query(Asset.ticker).all()}
        session.add_all(Asset(ticker=ticker, name=name) for ticker, name in DEFAULT_ASSETS.items() if ticker not in existing)
        session.commit()


def _ensure_analysis_columns() -> None:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE analyses ADD COLUMN IF NOT EXISTS direction VARCHAR(20)"))
        connection.execute(text("ALTER TABLE analyses ADD COLUMN IF NOT EXISTS time_horizon VARCHAR(20)"))
