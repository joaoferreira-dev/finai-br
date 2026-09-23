import json
import logging
import re
from pathlib import Path
from typing import TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from openai import OpenAI
import yaml

from agents.schemas import ResearchEvidence, TickerAnalysis
from ingestion.news import NewsItem, deduplicate_news, normalize_text
from settings import Settings

logger = logging.getLogger(__name__)


class WorkflowState(TypedDict):
    ticker: str
    price: dict
    news: list[dict]
    research_summary: list[ResearchEvidence]
    analysis: TickerAnalysis


PROMPT_DIR = Path(__file__).parent / "prompt"
CITATION_RE = re.compile(r"\[(\d+)\]")


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


def _all_texts(analysis: TickerAnalysis) -> list[str]:
    texts = [analysis.rationale, analysis.summary, *analysis.risks, *analysis.limitations]
    for point in [*analysis.catalysts, *analysis.risk_details]:
        texts.extend([point.text, point.mechanism])
    for forecast in analysis.forecasts:
        texts.extend([forecast.broker, forecast.metric_type, forecast.value, *forecast.assumptions])
    return [text for text in texts if text]


def _referenced_ids(texts: list[str]) -> set[int]:
    return {int(value) for text in texts for value in CITATION_RE.findall(text)}


def _validate_claim_citations(analysis: TickerAnalysis, research_ids: set[int]) -> None:
    """Require every evidence-backed claim to resolve to its supporting research."""
    if research_ids and not _referenced_ids([analysis.rationale, analysis.summary]):
        raise ValueError("síntese sem citação de evidência")
    for text in analysis.risks:
        if not _referenced_ids([text]):
            raise ValueError("risco sem citação de evidência")
    for point in [*analysis.catalysts, *analysis.risk_details]:
        if not (set(point.source_ids) | _referenced_ids([point.text])).intersection(research_ids):
            raise ValueError("catalisador ou risco estruturado sem fonte")
    for forecast in analysis.forecasts:
        if not (set(forecast.source_ids) | _referenced_ids([forecast.broker, forecast.metric_type, forecast.value, *forecast.assumptions])).intersection(research_ids):
            raise ValueError("projeção sem fonte atribuída")


def _valid_excerpt(excerpt: str, news_item: dict) -> bool:
    candidate = normalize_text(excerpt).casefold()
    source_text = " ".join((news_item.get("title", ""), news_item.get("summary", ""))).casefold()
    return bool(candidate and candidate in source_text)


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
        numbered = _number_news(state["news"])
        messages = _as_openai_messages(self.research_prompt, {
            "ticker": state["ticker"],
            "news": json.dumps(numbered, ensure_ascii=False),
        })
        for attempt in range(2):
            try:
                response = self.ask(messages)
                raw_items = _parse_json_response(response, list)
                research = [ResearchEvidence.model_validate(item) for item in raw_items]
                for item in research:
                    ids = {item.source_id, *item.related_source_ids}
                    if not ids.issubset(set(range(1, len(numbered) + 1))):
                        raise ValueError("pesquisa referencia fonte inexistente")
                    source = numbered[item.source_id - 1]
                    if not _valid_excerpt(item.supporting_excerpt, source):
                        raise ValueError("trecho de apoio não encontrado na notícia RSS")
                return {"research_summary": [item for item in research if item.relevance.casefold() != "irrelevante"]}
            except Exception as error:
                logger.warning("Pesquisa inválida para %s (tentativa %d): %s", state["ticker"], attempt + 1, type(error).__name__)
                if attempt == 0:
                    messages = _with_repair(messages, error)
        logger.error("Pesquisa indisponível para %s após tentativa de correção", state["ticker"])
        return {"research_summary": []}

    def analyse(self, state: WorkflowState) -> dict:
        price = {**state["price"], "trading_date": state["price"]["trading_date"].isoformat()}
        news = _number_news(state["news"])
        messages = _as_openai_messages(self.analyse_prompt, {
            "ticker": state["ticker"],
            "price": json.dumps(price, ensure_ascii=False, allow_nan=False),
            "research_summary": json.dumps([item.model_dump() for item in state["research_summary"]], ensure_ascii=False),
            "news": json.dumps(news, ensure_ascii=False),
        })
        for attempt in range(2):
            try:
                response = self.ask(messages)
                analysis = TickerAnalysis.model_validate(_parse_json_response(response, dict))
                texts = _all_texts(analysis)
                cited_ids = _referenced_ids(texts)
                listed_ids = set(analysis.source_ids)
                for point in [*analysis.catalysts, *analysis.risk_details, *analysis.forecasts]:
                    listed_ids.update(point.source_ids)
                valid_ids = set(range(1, len(news) + 1))
                if not cited_ids.issubset(valid_ids) or not listed_ids.issubset(valid_ids):
                    raise ValueError("análise referencia fonte inexistente")
                research_ids = {
                    source_id
                    for item in state["research_summary"]
                    for source_id in {item.source_id, *item.related_source_ids}
                }
                _validate_claim_citations(analysis, research_ids)
                if not (cited_ids | listed_ids).issubset(research_ids):
                    raise ValueError("análise cita notícia sem evidência validada")
                analysis.source_ids = sorted(cited_ids | listed_ids)
                return {"analysis": analysis}
            except Exception as error:
                logger.warning("Análise inválida para %s (tentativa %d): %s", state["ticker"], attempt + 1, type(error).__name__)
                if attempt == 0:
                    messages = _with_repair(messages, error)
        logger.error("Análise indisponível para %s após tentativa de correção", state["ticker"])
        return {"analysis": TickerAnalysis(
            direction="neutro", confidence=0, time_horizon="incerto",
            rationale="Análise indisponível: a resposta não passou pela validação de evidências.",
            summary="Não foi possível validar uma análise para este ativo.",
            limitations=["Análise indisponível após tentativa de correção da resposta."],
        )}

    def invoke(self, ticker: str, price: dict, news: list[NewsItem]) -> TickerAnalysis:
        clean_news = deduplicate_news(news)
        output = self.graph.invoke({
            "ticker": ticker, "price": price,
            "news": [item.model_dump(mode="json") for item in clean_news],
        })
        analysis = output["analysis"]
        analysis.research_evidence = output["research_summary"]
        research_ids = {
            source_id
            for item in output["research_summary"]
            for source_id in {item.source_id, *item.related_source_ids}
        }
        analysis.source_ids = sorted(set(analysis.source_ids) | research_ids)
        return analysis


def _with_repair(messages: list[dict[str, str]], error: Exception) -> list[dict[str, str]]:
    return [*messages, {
        "role": "user",
        "content": f"Corrija a resposta anterior. Problema de validação: {type(error).__name__}. "
                   "Retorne somente o JSON solicitado, usando apenas as fontes fornecidas.",
    }]


def _number_news(news: list[dict]) -> list[dict]:
    numbered = []
    for index, item in enumerate(news, start=1):
        numbered.append({"source_id": index, "content_type": "rss_excerpt", **item})
    return numbered


def _parse_json_response(response: str, expected_type: type) -> object:
    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE).strip()
    decoder = json.JSONDecoder()
    for index, character in enumerate(cleaned):
        if character not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(cleaned[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, expected_type):
            return value
    raise ValueError(f"A resposta do modelo não contém JSON {expected_type.__name__} válido")
