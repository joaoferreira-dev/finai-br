"""Normalize daily quotations and calculate historical market context."""

from dataclasses import dataclass
from datetime import date
from math import isfinite
from typing import Literal

from pydantic import BaseModel, Field, model_validator


@dataclass(frozen=True)
class DailyObservation:
    trading_date: date
    close: float | None
    adjusted_close: float | None
    volume: int | None
    close_conflict: bool = False
    adjusted_conflict: bool = False
    volume_conflict: bool = False


class HistoricalMetric(BaseModel):
    value: float | None = None
    reason: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    observation_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_value(self) -> "HistoricalMetric":
        if self.value is not None and not isfinite(self.value):
            raise ValueError("A métrica histórica deve ser finita")
        if (self.value is None) == (self.reason is None):
            raise ValueError("A métrica deve ter valor ou motivo de indisponibilidade")
        return self


class HistoricalContext(BaseModel):
    provider: Literal["yfinance", "brapi"]
    price_basis: Literal["adjusted_close"] = "adjusted_close"
    as_of_date: date
    change_5_sessions: HistoricalMetric
    change_30_sessions: HistoricalMetric
    average_volume_20_sessions: HistoricalMetric
    volume_ratio_20_sessions: HistoricalMetric


def positive_price(value: object) -> float | None:
    """Return a usable daily price without inventing a replacement."""
    try:
        price = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return price if isfinite(price) and price > 0 else None


def nonnegative_volume(value: object) -> int | None:
    """Keep zero-volume sessions while rejecting absent or invalid volumes."""
    try:
        amount = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return int(amount) if isfinite(amount) and amount >= 0 and amount.is_integer() else None


def normalize_observations(rows: list[DailyObservation]) -> list[DailyObservation]:
    """Sort sessions and invalidate fields with conflicting duplicate values."""
    by_date: dict[date, DailyObservation] = {}
    for row in rows:
        previous = by_date.get(row.trading_date)
        if previous is None:
            by_date[row.trading_date] = row
            continue
        close_conflict = previous.close_conflict or row.close_conflict or previous.close != row.close
        adjusted_conflict = (
            previous.adjusted_conflict or row.adjusted_conflict
            or previous.adjusted_close != row.adjusted_close
        )
        volume_conflict = previous.volume_conflict or row.volume_conflict or previous.volume != row.volume
        by_date[row.trading_date] = DailyObservation(
            trading_date=row.trading_date,
            close=None if close_conflict else previous.close,
            adjusted_close=None if adjusted_conflict else previous.adjusted_close,
            volume=None if volume_conflict else previous.volume,
            close_conflict=close_conflict,
            adjusted_conflict=adjusted_conflict,
            volume_conflict=volume_conflict,
        )
    return sorted(by_date.values(), key=lambda row: row.trading_date)


def _unavailable(
    reason: str, rows: list[DailyObservation], field: str, *, maximum: int
) -> HistoricalMetric:
    selected = rows[-maximum:]
    return HistoricalMetric(
        reason=reason,
        start_date=selected[0].trading_date if selected else None,
        end_date=selected[-1].trading_date if selected else None,
        observation_count=sum(getattr(row, field) is not None for row in selected),
    )


def _price_change(rows: list[DailyObservation], sessions: int) -> HistoricalMetric:
    required = sessions + 1
    if len(rows) < required:
        return _unavailable("histórico insuficiente", rows, "adjusted_close", maximum=required)
    window = rows[-required:]
    if any(row.adjusted_close is None for row in window):
        reason = (
            "dados conflitantes na mesma data" if any(row.adjusted_conflict for row in window)
            else "preço ajustado ausente ou inválido"
        )
        return _unavailable(reason, window, "adjusted_close", maximum=required)
    change = (window[-1].adjusted_close / window[0].adjusted_close - 1) * 100
    if not isfinite(change):
        return _unavailable("preço ajustado inválido", window, "adjusted_close", maximum=required)
    return HistoricalMetric(
        value=change,
        start_date=window[0].trading_date,
        end_date=window[-1].trading_date,
        observation_count=required,
    )


def _average_volume(rows: list[DailyObservation]) -> HistoricalMetric:
    previous = rows[:-1]
    if len(previous) < 20:
        return _unavailable("histórico insuficiente", previous, "volume", maximum=20)
    window = previous[-20:]
    if any(row.volume is None for row in window):
        reason = (
            "dados conflitantes na mesma data" if any(row.volume_conflict for row in window)
            else "volume ausente ou inválido"
        )
        return _unavailable(reason, window, "volume", maximum=20)
    return HistoricalMetric(
        value=sum(row.volume for row in window) / 20,
        start_date=window[0].trading_date,
        end_date=window[-1].trading_date,
        observation_count=20,
    )


def calculate_context(rows: list[DailyObservation], provider: Literal["yfinance", "brapi"]) -> HistoricalContext:
    """Use the same session windows for either quotation provider."""
    if not rows:
        raise ValueError("Sem cotações para calcular o contexto")
    current = rows[-1]
    average = _average_volume(rows)
    if average.value is None:
        ratio = HistoricalMetric(
            reason=average.reason,
            start_date=average.start_date,
            end_date=current.trading_date,
            observation_count=average.observation_count,
        )
    elif current.volume is None:
        ratio = HistoricalMetric(
            reason="volume atual ausente ou inválido",
            start_date=average.start_date,
            end_date=current.trading_date,
            observation_count=20,
        )
    elif average.value == 0:
        ratio = HistoricalMetric(
            reason="média de volume igual a zero",
            start_date=average.start_date,
            end_date=current.trading_date,
            observation_count=20,
        )
    else:
        value = current.volume / average.value
        ratio = HistoricalMetric(
            value=value if isfinite(value) else None,
            reason=None if isfinite(value) else "volume inválido",
            start_date=average.start_date,
            end_date=current.trading_date,
            observation_count=21,
        )
    return HistoricalContext(
        provider=provider,
        as_of_date=current.trading_date,
        change_5_sessions=_price_change(rows, 5),
        change_30_sessions=_price_change(rows, 30),
        average_volume_20_sessions=average,
        volume_ratio_20_sessions=ratio,
    )


def quotation_from_rows(rows: list[DailyObservation], provider: Literal["yfinance", "brapi"]) -> dict:
    """Produce today's quotation and compact historical context."""
    observations = normalize_observations(rows)
    if not observations or observations[-1].close is None:
        raise ValueError("Fechamento atual ausente ou conflitante")
    current = observations[-1]
    previous_close = observations[-2].close if len(observations) > 1 else None
    change_percent = (
        (current.close / previous_close - 1) * 100 if previous_close is not None else None
    )
    if change_percent is not None and not isfinite(change_percent):
        change_percent = None
    return {
        "trading_date": current.trading_date,
        "close": current.close,
        "change_percent": change_percent,
        "volume": current.volume,
        "historical_context": calculate_context(observations, provider).model_dump(mode="json"),
    }
