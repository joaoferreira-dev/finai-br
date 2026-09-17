from enum import StrEnum

from pydantic import BaseModel, Field


class Sentiment(StrEnum):
    STRONG_BULLISH = "Alta Confiança de Alta"
    MODERATE = "Moderado"
    NEUTRAL = "Neutro"
    MODERATE_BEARISH = "Moderado de Baixa"
    STRONG_BEARISH = "Alta Confiança de Baixa"


class TickerAnalysis(BaseModel):
    sentiment: Sentiment
    confidence: int = Field(ge=0, le=100)
    rationale: str = Field(min_length=1, max_length=1000)
    risks: list[str] = Field(default_factory=list)
