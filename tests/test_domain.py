import pytest
from pydantic import ValidationError

from agents.schemas import Sentiment, TickerAnalysis


def test_structured_analysis_accepts_prd_sentiment() -> None:
    result = TickerAnalysis.model_validate({"sentiment": "Moderado", "confidence": 71, "rationale": "Notícias mistas", "risks": ["volatilidade"]})
    assert result.sentiment is Sentiment.MODERATE


def test_structured_analysis_rejects_invalid_sentiment() -> None:
    with pytest.raises(ValidationError):
        TickerAnalysis.model_validate({"sentiment": "Comprar", "confidence": 50, "rationale": "x"})
