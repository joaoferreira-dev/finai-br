from database import session


def test_initialise_database_creates_missing_default_assets(monkeypatch) -> None:
    created = False
    added_assets = []

    class FakeMetadata:
        def create_all(self, engine):
            nonlocal created
            created = True

    class FakeQuery:
        def all(self):
            return [("PETR4",)]

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def query(self, model):
            return FakeQuery()

        def add_all(self, assets):
            added_assets.extend(assets)

        def commit(self):
            pass

    monkeypatch.setattr(session.Base, "metadata", FakeMetadata())
    monkeypatch.setattr(session, "SessionLocal", FakeSession)
    monkeypatch.setattr(session, "_ensure_analysis_columns", lambda: None)

    session.initialise_database()

    assert created
    assert [asset.ticker for asset in added_assets] == ["BBAS3", "VALE3", "ITUB4", "CSMG3"]