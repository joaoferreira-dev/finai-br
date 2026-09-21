from enum import StrEnum

from pydantic import BaseModel, Field


class Sentiment(StrEnum):
    STRONG_BULLISH = "Alta Confiança de Alta"
    MODERATE = "Moderado"
    NEUTRAL = "Neutro"
    MODERATE_BEARISH = "Moderado de Baixa"
    STRONG_BEARISH = "Alta Confiança de Baixa"


class Direction(StrEnum):
    BULLISH = "alta"
    NEUTRAL = "neutro"
    BEARISH = "baixa"


class TimeHorizon(StrEnum):
    SHORT = "curto_prazo"
    MEDIUM = "medio_prazo"
    LONG = "longo_prazo"
    MIXED = "misto"
    UNCERTAIN = "incerto"


class ResearchEvidence(BaseModel):
    source_id: int = Field(ge=1)
    summary: str = Field(min_length=1, max_length=1000)
    relevance: str
    potential_impact: str
    horizon: str
    key_facts: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)


class TickerAnalysis(BaseModel):
    direction: Direction
    confidence: int = Field(ge=0, le=100)
    time_horizon: TimeHorizon
    rationale: str = Field(min_length=1, max_length=1000)
    risks: list[str] = Field(default_factory=list)
    source_ids: list[int] = Field(default_factory=list)
