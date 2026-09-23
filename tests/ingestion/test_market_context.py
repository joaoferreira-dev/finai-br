from datetime import date, datetime, timedelta, timezone
from io import BytesIO
import json
from urllib.error import HTTPError

import pandas as pd
import pytest

from ingestion import market_data
from ingestion.market_context import DailyObservation, quotation_from_rows


def observations(count: int, *, start: date = date(2026, 7, 1)) -> list[DailyObservation]:
    days = pd.bdate_range(start=start, periods=count)
    return [
        DailyObservation(day.date(), 100 + index, 50 + index, 1000 + 10 * index)
        for index, day in enumerate(days)
    ]


@pytest.mark.parametrize("count,available", [(5, False), (6, True), (20, True), (21, True), (30, True), (31, True)])
def test_price_window_requires_reference_session(count: int, available: bool) -> None:
    rows = observations(count)
    context = quotation_from_rows(rows, "yfinance")["historical_context"]
    short = context["change_5_sessions"]
    long = context["change_30_sessions"]
    assert (short["value"] is not None) is available
    assert (long["value"] is not None) is (count >= 31)
    if available:
        assert short["value"] == pytest.approx((rows[-1].adjusted_close / rows[-6].adjusted_close - 1) * 100)
        assert short["start_date"] == rows[-6].trading_date.isoformat()
        assert short["end_date"] == rows[-1].trading_date.isoformat()
        assert short["observation_count"] == 6
    else:
        assert short["reason"] == "histórico insuficiente"
    if count == 31:
        assert long["start_date"] == rows[0].trading_date.isoformat()
        assert long["observation_count"] == 31


@pytest.mark.parametrize("count,expected", [(20, False), (21, True)])
def test_volume_window_excludes_current_session(count: int, expected: bool) -> None:
    rows = observations(count)
    context = quotation_from_rows(rows, "yfinance")["historical_context"]
    average = context["average_volume_20_sessions"]
    ratio = context["volume_ratio_20_sessions"]
    assert (average["value"] is not None) is expected
    if expected:
        assert average["value"] == pytest.approx(sum(row.volume for row in rows[:-1]) / 20)
        assert ratio["value"] == pytest.approx(rows[-1].volume / average["value"])
        assert average["end_date"] == rows[-2].trading_date.isoformat()
        assert ratio["end_date"] == rows[-1].trading_date.isoformat()
    else:
        assert ratio["reason"] == "histórico insuficiente"


def test_weekend_and_holiday_gaps_do_not_create_sessions() -> None:
    rows = observations(6)
    rows = [
        row if index < 3 else DailyObservation(row.trading_date + timedelta(days=2), row.close, row.adjusted_close, row.volume)
        for index, row in enumerate(rows)
    ]
    result = quotation_from_rows(list(reversed(rows)), "brapi")
    assert result["trading_date"] == rows[-1].trading_date
    assert result["historical_context"]["change_5_sessions"]["start_date"] == rows[0].trading_date.isoformat()
    assert result["historical_context"]["change_5_sessions"]["observation_count"] == 6


def test_missing_fields_stay_in_windows_without_extending_them() -> None:
    rows = observations(32)
    rows[2] = DailyObservation(rows[2].trading_date, rows[2].close, None, rows[2].volume)
    rows[-3] = DailyObservation(rows[-3].trading_date, rows[-3].close, rows[-3].adjusted_close, None)
    context = quotation_from_rows(rows, "yfinance")["historical_context"]
    assert context["change_5_sessions"]["value"] is not None
    assert context["change_30_sessions"]["value"] is None
    assert context["change_30_sessions"]["reason"] == "preço ajustado ausente ou inválido"
    assert context["average_volume_20_sessions"]["value"] is None
    assert context["volume_ratio_20_sessions"]["value"] is None


def test_zero_volume_is_valid_but_zero_baseline_has_no_ratio() -> None:
    rows = [DailyObservation(row.trading_date, row.close, row.adjusted_close, 0) for row in observations(21)]
    context = quotation_from_rows(rows, "brapi")["historical_context"]
    assert context["average_volume_20_sessions"]["value"] == 0
    assert context["volume_ratio_20_sessions"]["reason"] == "média de volume igual a zero"
    rows[0] = DailyObservation(rows[0].trading_date, rows[0].close, rows[0].adjusted_close, 100)
    context = quotation_from_rows(rows, "brapi")["historical_context"]
    assert context["volume_ratio_20_sessions"]["value"] == 0


def test_duplicate_date_conflicts_invalidate_only_affected_fields() -> None:
    rows = observations(31)
    duplicate = DailyObservation(rows[5].trading_date, rows[5].close, 999, rows[5].volume)
    context = quotation_from_rows(rows + [duplicate], "yfinance")["historical_context"]
    assert context["change_30_sessions"]["reason"] == "dados conflitantes na mesma data"
    assert context["change_5_sessions"]["value"] is not None
    assert context["average_volume_20_sessions"]["value"] is not None


def test_conflicting_current_close_cannot_be_selected_as_quote() -> None:
    rows = observations(2)
    duplicate = DailyObservation(rows[-1].trading_date, 999, rows[-1].adjusted_close, rows[-1].volume)
    with pytest.raises(ValueError, match="conflitante"):
        quotation_from_rows(rows + [duplicate], "yfinance")


def test_absent_or_invalid_values_are_not_replaced_by_zero() -> None:
    rows = [DailyObservation(date(2026, 9, 18), 100, None, None)]
    result = quotation_from_rows(rows, "brapi")
    assert result["change_percent"] is None
    assert result["volume"] is None
    assert result["historical_context"]["change_5_sessions"]["value"] is None
    assert market_data.positive_price(float("inf")) is None
    assert market_data.positive_price(float("nan")) is None
    assert market_data.nonnegative_volume(float("nan")) is None
    assert market_data.nonnegative_volume(-1) is None
    assert market_data.nonnegative_volume(0) == 0


def test_providers_normalize_to_same_metrics_including_adjusted_prices(monkeypatch) -> None:
    rows = observations(31)
    history = pd.DataFrame(
        {
            "Close": [row.close for row in rows],
            "Adj Close": [row.adjusted_close for row in rows],
            "Volume": [row.volume for row in rows],
        },
        index=pd.to_datetime([row.trading_date for row in rows]),
    )

    class FakeTicker:
        def history(self, **kwargs):
            assert kwargs == {"period": "3mo", "interval": "1d", "auto_adjust": False}
            return history

    class FakeResponse(BytesIO):
        def __enter__(self):
            return self

    def fake_urlopen(request, timeout):
        assert "range=3mo" in request.full_url
        payload = {"results": [{"historicalDataPrice": [
            {"date": int(datetime.combine(row.trading_date, datetime.min.time(), timezone.utc).timestamp()),
             "close": row.close, "adjustedClose": row.adjusted_close, "volume": row.volume}
            for row in reversed(rows)
        ]}]}
        return FakeResponse(json.dumps(payload).encode())

    monkeypatch.setattr(market_data.yf, "Ticker", lambda ticker: FakeTicker())
    monkeypatch.setattr(market_data, "urlopen", fake_urlopen)
    monkeypatch.setattr(market_data, "get_settings", lambda: type("Settings", (), {"brapi_token": ""})())
    yahoo = market_data._fetch_price_yfinance("PETR4")
    brapi = market_data._fetch_price_brapi("PETR4")
    assert yahoo["close"] == brapi["close"]
    assert yahoo["change_percent"] == brapi["change_percent"]
    assert yahoo["historical_context"]["change_5_sessions"] == brapi["historical_context"]["change_5_sessions"]
    assert yahoo["historical_context"]["change_30_sessions"] == brapi["historical_context"]["change_30_sessions"]
    assert yahoo["historical_context"]["volume_ratio_20_sessions"] == brapi["historical_context"]["volume_ratio_20_sessions"]
    assert yahoo["historical_context"]["change_30_sessions"]["value"] != pytest.approx((rows[-1].close / rows[0].close - 1) * 100)


def test_brapi_rejected_extended_range_retries_short_history(monkeypatch) -> None:
    requests = []

    class FakeResponse(BytesIO):
        def __enter__(self):
            return self

    def fake_urlopen(request, timeout):
        requests.append(request.full_url)
        if "range=3mo" in request.full_url:
            raise HTTPError(request.full_url, 403, "range denied", None, None)
        payload = {"results": [{"historicalDataPrice": [
            {"date": int(datetime(2026, 9, 18, tzinfo=timezone.utc).timestamp()),
             "close": 42, "volume": None}
        ]}]}
        return FakeResponse(json.dumps(payload).encode())

    monkeypatch.setattr(market_data, "urlopen", fake_urlopen)
    monkeypatch.setattr(market_data, "get_settings", lambda: type("Settings", (), {"brapi_token": ""})())
    result = market_data._fetch_price_brapi("PETR4")
    assert len(requests) == 2
    assert "range=5d" in requests[-1]
    assert result["historical_context"]["change_30_sessions"]["value"] is None
    assert result["volume"] is None
