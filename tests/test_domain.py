import pytest
from pydantic import ValidationError

from agents.schemas import Direction, TickerAnalysis


def test_structured_analysis_accepts_prd_sentiment() -> None:
    result = TickerAnalysis.model_validate({"direction": "neutro", "confidence": 71, "time_horizon": "incerto", "rationale": "Notícias mistas", "risks": ["volatilidade"]})
    assert result.direction is Direction.NEUTRAL


def test_structured_analysis_rejects_invalid_sentiment() -> None:
    with pytest.raises(ValidationError):
        TickerAnalysis.model_validate({"sentiment": "Comprar", "confidence": 50, "rationale": "x"})
