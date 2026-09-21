from datetime import date

import pytest

from agents import market_workflow
from agents.schemas import Sentiment
from ingestion.news import NewsItem
from settings import Settings


class FakeResponse:
    def __init__(self, content: str):
        self.choices = [type("Choice", (), {"message": type("Message", (), {"content": content})()})()]


class FakeCompletions:
    def __init__(self, responses: list[str]):
        self.responses = iter(responses)

    def create(self, **kwargs):
        return FakeResponse(next(self.responses))


class FakeClient:
    def __init__(self, responses: list[str]):
        self.chat = type("Chat", (), {"completions": FakeCompletions(responses)})()


class FakeAPIError(Exception):
    def __init__(self, status_code: int):
        self.status_code = status_code


def test_workflow_requires_provider_credentials() -> None:
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        market_workflow.MarketWorkflow(Settings(groq_api_key=""))

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        market_workflow.MarketWorkflow(Settings(llm_provider="openai"))

    with pytest.raises(RuntimeError, match="LLM_PROVIDER"):
        market_workflow.MarketWorkflow(Settings(llm_provider="other"))


def test_workflow_invokes_researcher_and_analyst(monkeypatch) -> None:
    monkeypatch.setattr(market_workflow, "OpenAI", lambda **kwargs: FakeClient([
        '[{"source_id":1,"summary":"Fato relevante","relevance":"alta","potential_impact":"misto","horizon":"incerto","key_facts":["Fato"],"uncertainties":["Incerteza"]}]',
        '{"direction":"neutro","confidence":72,"time_horizon":"incerto","rationale":"Dados mistos [1]","risks":["volatilidade"],"source_ids":[1]}',
    ]))
    workflow = market_workflow.MarketWorkflow(Settings(groq_api_key="test-key"))

    result = workflow.invoke(
        "PETR4",
        {"trading_date": date(2026, 9, 17), "close": 35.2, "change_percent": 1.5, "volume": 1000},
        [NewsItem(title="Fato", link="https://example.com")],
    )

    assert result.direction.value == "neutro"
    assert result.confidence == 72
    assert result.risks == ["volatilidade"]
    assert result.source_ids == [1]


def test_workflow_supports_openai_configuration(monkeypatch) -> None:
    client = FakeClient([])
    monkeypatch.setattr(market_workflow, "OpenAI", lambda **kwargs: client)

    workflow = market_workflow.MarketWorkflow(Settings(llm_provider="openai", openai_api_key="test-key"))

    assert workflow.client is client
    assert workflow.model == "gpt-4o-mini"


@pytest.mark.parametrize(
    ("status_code", "message"),
    [
        (404, "modelo Groq"),
        (403, "GROQ_API_KEY"),
    ],
)
def test_workflow_reports_groq_api_configuration_errors(monkeypatch, status_code: int, message: str) -> None:
    class FailingCompletions:
        def create(self, **kwargs):
            raise FakeAPIError(status_code)

    monkeypatch.setattr(market_workflow, "OpenAI", lambda **kwargs: type("Client", (), {
        "chat": type("Chat", (), {"completions": FailingCompletions()})()
    })())
    workflow = market_workflow.MarketWorkflow(Settings(groq_api_key="test-key"))

    with pytest.raises(RuntimeError, match=message):
        workflow.ask([{"role": "user", "content": "teste"}])