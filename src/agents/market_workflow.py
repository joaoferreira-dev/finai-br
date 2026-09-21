import json
import re
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langchain_core.prompts import ChatPromptTemplate
from openai import OpenAI
import yaml

from agents.schemas import ResearchEvidence, TickerAnalysis
from ingestion.news import NewsItem
from settings import Settings


class WorkflowState(TypedDict):
    ticker: str
    price: dict
    news: list[dict]
    research_summary: list[ResearchEvidence]
    analysis: TickerAnalysis


PROMPT_DIR = Path(__file__).parent / "prompt"


def _load_prompt(name: str) -> ChatPromptTemplate:
    with (PROMPT_DIR / f"{name}.yaml").open(encoding="utf-8") as prompt_file:
        definition = yaml.safe_load(prompt_file)
    return ChatPromptTemplate.from_messages(
        [(message["role"], message["content"]) for message in definition["messages"]]
    )


def _as_openai_messages(prompt: ChatPromptTemplate, values: dict) -> list[dict[str, str]]:
    role_map = {"human": "user", "ai": "assistant", "system": "system"}
    return [
        {"role": role_map[message.type], "content": message.content}
        for message in prompt.invoke(values).to_messages()
    ]


class MarketWorkflow:
    """Grafo com os papéis de pesquisador e analista financeiro."""

    def __init__(self, settings: Settings):
        if settings.llm_provider == "groq":
            if not settings.groq_api_key:
                raise RuntimeError("GROQ_API_KEY não configurada")
            self.client = OpenAI(api_key=settings.groq_api_key, base_url="https://api.groq.com/openai/v1")
            self.model = settings.groq_model
        elif settings.llm_provider == "openai":
            if not settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY não configurada")
            self.client, self.model = OpenAI(api_key=settings.openai_api_key), settings.openai_model
        else:
            raise RuntimeError("LLM_PROVIDER deve ser 'groq' ou 'openai'")
        self.research_prompt = _load_prompt("research")
        self.analyse_prompt = _load_prompt("analyse")
        graph = StateGraph(WorkflowState)
        graph.add_node("research", self.research)
        graph.add_node("analyse", self.analyse)
        graph.add_edge(START, "research")
        graph.add_edge("research", "analyse")
        graph.add_edge("analyse", END)
        self.graph = graph.compile()

    def ask(self, prompt: list[dict[str, str]]) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model, temperature=0.2, messages=prompt
            )
        except Exception as error:
            status_code = getattr(error, "status_code", None)
            if status_code == 404:
                raise RuntimeError(
                    f"O modelo Groq '{self.model}' não está disponível. "
                    "Atualize GROQ_MODEL no .env para um modelo ativo na sua conta."
                ) from error
            if status_code in {401, 403}:
                raise RuntimeError(
                    "A chave GROQ_API_KEY foi rejeitada. Gere uma nova chave no console.groq.com "
                    "e atualize o arquivo .env."
                ) from error
            raise
        return response.choices[0].message.content or ""

    def research(self, state: WorkflowState) -> dict:
        response = self.ask(_as_openai_messages(self.research_prompt, {
            "ticker": state["ticker"],
            "news": json.dumps(_number_news(state["news"]), ensure_ascii=False),
        }))
        research = [ResearchEvidence.model_validate(item) for item in json.loads(response)]
        valid_ids = set(range(1, len(state["news"]) + 1))
        return {"research_summary": [item for item in research if item.source_id in valid_ids]}

    def analyse(self, state: WorkflowState) -> dict:
        price = {**state["price"], "trading_date": state["price"]["trading_date"].isoformat()}
        response = self.ask(_as_openai_messages(self.analyse_prompt, {
            "ticker": state["ticker"],
            "price": json.dumps(price, ensure_ascii=False),
            "research_summary": json.dumps([item.model_dump() for item in state["research_summary"]], ensure_ascii=False),
            "news": json.dumps(_number_news(state["news"]), ensure_ascii=False),
        }))
        analysis = TickerAnalysis.model_validate_json(response)
        valid_ids = set(range(1, len(state["news"]) + 1))
        analysis.source_ids = sorted({source_id for source_id in analysis.source_ids if source_id in valid_ids})
        cited_ids = {int(value) for value in re.findall(r"\[(\d+)\]", analysis.rationale)}
        analysis.source_ids = sorted(set(analysis.source_ids) | (cited_ids & valid_ids))
        return {"analysis": analysis}

    def invoke(self, ticker: str, price: dict, news: list[NewsItem]) -> TickerAnalysis:
        output = self.graph.invoke({"ticker": ticker, "price": price, "news": [item.model_dump(mode="json") for item in news]})
        return output["analysis"]


def _number_news(news: list[dict]) -> list[dict]:
    return [{"source_id": index, **item} for index, item in enumerate(news, start=1)]
