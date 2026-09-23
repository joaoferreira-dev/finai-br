from types import SimpleNamespace

from delivery import email
from settings import Settings


def test_send_latest_report_skips_when_email_is_disabled(monkeypatch) -> None:
    monkeypatch.setattr(email, "get_settings", lambda: Settings(email_enabled=False))

    class UnexpectedSession:
        def __enter__(self):
            raise AssertionError("A sessão não deveria ser aberta")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(email, "SessionLocal", UnexpectedSession)
    email.send_latest_report()


def test_send_latest_report_skips_when_there_are_no_analyses(monkeypatch) -> None:
    monkeypatch.setattr(email, "get_settings", lambda: Settings(email_enabled=True))

    class EmptySession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query):
            return SimpleNamespace(all=lambda: [])

    monkeypatch.setattr(email, "SessionLocal", EmptySession)
    email.send_latest_report()


def test_send_latest_report_formats_latest_analysis(monkeypatch) -> None:
    settings = Settings(
        email_enabled=True,
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="user",
        smtp_password="password",
        email_from="from@example.com",
        email_to="to@example.com",
    )
    analysis = SimpleNamespace(analysis_date=__import__("datetime").date(2026, 9, 16), sentiment="Moderado", confidence=72, rationale="Dados mistos")
    asset = SimpleNamespace(ticker="PETR4")
    price = SimpleNamespace(close=35.2, change_percent=1.5)

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query):
            class FakeRow:
                Analysis = analysis
                Asset = asset
                Price = price

                def __iter__(self):
                    return iter((self.Analysis, self.Asset, self.Price))

            return SimpleNamespace(all=lambda: [FakeRow()])

    class FakeSMTP:
        def __init__(self, host, port):
            assert (host, port) == ("smtp.example.com", 587)
            self.message = None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            pass

        def login(self, username, password):
            assert (username, password) == ("user", "password")

        def send_message(self, message):
            self.message = message
            assert message["To"] == "to@example.com"
            parts = {part.get_content_type(): part.get_content() for part in message.walk() if part.get_content_type() in {"text/plain", "text/html"}}
            assert "PETR4: Moderado" in parts["text/plain"]
            assert "Qualidade da evidência" in parts["text/plain"]
            assert "Panorama diário" in parts["text/html"]

    monkeypatch.setattr(email, "get_settings", lambda: settings)
    monkeypatch.setattr(email, "SessionLocal", FakeSession)
    monkeypatch.setattr(email.smtplib, "SMTP", FakeSMTP)

    email.send_latest_report()
