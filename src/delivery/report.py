import html
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

from pydantic import ValidationError

from ingestion.market_context import HistoricalContext, HistoricalMetric


@dataclass(frozen=True)
class ReportSource:
    title: str
    link: str
    published_at: datetime | None = None
    source_id: int = 0
    publisher: str = ""


@dataclass(frozen=True)
class ReportItem:
    ticker: str
    analysis_date: date
    sentiment: str
    time_horizon: str | None
    confidence: int
    rationale: str
    risks: list[str]
    close: float
    change_percent: float | None
    sources: list[ReportSource]
    volume: int | None = None
    historical_context: HistoricalContext | None = None
    summary: str = ""
    catalysts: list[dict] = field(default_factory=list)
    risk_details: list[dict] = field(default_factory=list)
    forecasts: list[dict] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    research_evidence: list[dict] = field(default_factory=list)
    quality_label: str = "legada"
    quality_explanation: str = "Análise legada sem classificação de qualidade da evidência."


TEMPLATE_PATH = Path(__file__).parent / "templates" / "report.html"
CITATION_RE = re.compile(r"\[(\d+)\]")


def _safe_link(link: str) -> str | None:
    parsed = urlparse(link)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return link
    return None


def _format_date(value: date | datetime | None) -> str:
    return value.strftime("%d/%m/%Y") if value else "Data não informada"


def _format_number(value: float, signed: bool = False) -> str:
    prefix = "+" if signed and value > 0 else ""
    return f"{prefix}{value:.2f}".replace(".", ",")


def _format_volume(value: int | float | None) -> str:
    if value is None:
        return "indisponível"
    return f"{value / 1_000_000:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " milhões de ações"


def _format_change(value: float | None) -> str:
    return f"{_format_number(value, signed=True)}%" if value is not None else "indisponível"


def _format_metric(metric: HistoricalMetric, *, suffix: str) -> str:
    if metric.value is None:
        return f"indisponível ({metric.reason})"
    period = (
        f" ({_format_date(metric.start_date)} a {_format_date(metric.end_date)})"
        if metric.start_date and metric.end_date else ""
    )
    return f"{_format_number(metric.value, signed=suffix == '%')}{suffix}{period}"


def _historical_metrics(item: ReportItem) -> list[tuple[str, str]]:
    context = item.historical_context
    if context is None:
        return [("Histórico", "indisponível (análise anterior às métricas históricas)")]
    ratio = context.volume_ratio_20_sessions
    ratio_text = _format_metric(ratio, suffix="×")
    if ratio.value is not None:
        average_metric = context.average_volume_20_sessions
        avg_dates = ""
        if average_metric.start_date and average_metric.end_date:
            avg_dates = f" de {_format_date(average_metric.start_date)} a {_format_date(average_metric.end_date)}"
        ratio_text = (
            f"{_format_number(ratio.value)}× (atual {_format_volume(item.volume)} em "
            f"{_format_date(context.as_of_date)}; média {_format_volume(average_metric.value)}{avg_dates})"
        )
    return [
        ("Cotação em", _format_date(context.as_of_date)),
        ("Variação ajustada em 5 pregões", _format_metric(context.change_5_sessions, suffix="%")),
        ("Variação ajustada em 30 pregões", _format_metric(context.change_30_sessions, suffix="%")),
        ("Volume vs. média dos 20 pregões anteriores", ratio_text),
        ("Fonte do histórico", context.provider),
        ("Base de retorno", "fechamento ajustado; janelas em pregões"),
    ]


def _display_direction(value: str) -> str:
    return {"alta": "Impacto positivo", "neutro": "Impacto neutro", "baixa": "Impacto negativo"}.get(value, value)


def _quality(confidence: int, evidence: list[dict]) -> tuple[str, str]:
    if not evidence:
        return "insuficiente", "Nenhuma evidência relevante passou pela validação; o conteúdo disponível se limita a trechos RSS."
    if confidence <= 20:
        label = "insuficiente"
    elif confidence <= 40:
        label = "fraca"
    elif confidence <= 60:
        label = "limitada"
    elif confidence <= 80:
        label = "razoavelmente forte"
    else:
        label = "forte"
    explanations = ["as fontes disponíveis são trechos RSS, sem acesso ao artigo integral"]
    if label in {"razoavelmente forte", "forte"}:
        label = "limitada"
    related = {related_id for item in evidence for related_id in item.get("related_source_ids", [])}
    if related:
        explanations.append("algumas notícias tratam do mesmo relatório ou evento")
    if any(item.get("uncertainties") for item in evidence):
        explanations.append("as fontes registram incertezas ou premissas ausentes")
    if not explanations:
        explanations.append("classifica a força das fontes, não a probabilidade de retorno")
    return label, "; ".join(explanations).capitalize() + "."


def _known_source_ids(item: ReportItem) -> set[int]:
    return {source.source_id for source in item.sources if source.source_id}


def _safe_citations(value: str, valid: set[int]) -> str:
    return CITATION_RE.sub(
        lambda match: match.group(0) if int(match.group(1)) in valid
        else f"[referência indisponível: {match.group(1)}]",
        value,
    )


def _refs(source_ids: list[int], valid: set[int]) -> str:
    return "".join(f" [{source_id}]" for source_id in sorted(set(source_ids)) if source_id in valid)


def _item_sections(item: ReportItem) -> list[tuple[str, list[str]]]:
    valid = _known_source_ids(item)
    summary = item.summary or item.rationale
    sections: list[tuple[str, list[str]]] = [
        ("Síntese", [_safe_citations(summary, valid)]),
    ]
    evidence = []
    for entry in item.research_evidence:
        text = _safe_citations(str(entry.get("summary", "")), valid)
        ids = [entry.get("source_id", 0), *entry.get("related_source_ids", [])]
        refs = _refs(ids, valid)
        related_note = " (cobertura relacionada; não é confirmação independente)" if len(set(ids)) > 1 else ""
        evidence.append(text + refs + related_note)
    if evidence:
        sections.append(("Evidências", evidence))
    if item.catalysts:
        sections.append(("Catalisadores", [
            _safe_citations(point.get("text", ""), valid) + _refs(point.get("source_ids", []), valid)
            + (f" — Mecanismo: {point['mechanism']}" if point.get("mechanism") else "")
            + (f" — Horizonte: {point['horizon']}" if point.get("horizon") else "")
            for point in item.catalysts
        ]))
    if item.risk_details or item.risks:
        detailed = [
            _safe_citations(point.get("text", ""), valid) + _refs(point.get("source_ids", []), valid)
            + (f" — Mecanismo: {point['mechanism']}" if point.get("mechanism") else "")
            + (f" — Horizonte: {point['horizon']}" if point.get("horizon") else "")
            for point in item.risk_details
        ]
        if not detailed:
            detailed = [_safe_citations(risk, valid) for risk in item.risks]
        sections.append(("Riscos", detailed))
    if item.forecasts:
        forecasts = []
        for forecast in item.forecasts:
            value = " ".join(part for part in [forecast.get("value", ""), forecast.get("unit", "")] if part)
            assumptions = "; premissas: " + "; ".join(forecast.get("assumptions", [])) if forecast.get("assumptions") else ""
            forecasts.append(
                f"{forecast.get('broker', 'Autor não informado')}: {forecast.get('metric_type', 'métrica não informada')} "
                f"{value}; horizonte: {forecast.get('horizon', 'incerto')}{assumptions}"
                + _refs(forecast.get("source_ids", []), valid)
            )
        sections.append(("Projeções atribuídas", forecasts))
    if item.limitations:
        sections.append(("Lacunas da análise", [_safe_citations(value, valid) for value in item.limitations]))
    sections.append(("Qualidade da evidência", [
        f"{item.quality_label.capitalize()}: {item.quality_explanation}"
    ]))
    return sections


def _format_source(source: ReportSource) -> str:
    prefix = f"[{source.source_id}] " if source.source_id else ""
    title = f"{prefix}{source.title}"
    publisher = f" — {source.publisher}" if source.publisher else ""
    date_label = _format_date(source.published_at)
    link = _safe_link(source.link)
    return f"- {title}{publisher} — {date_label}" + (f" ({link})" if link else "")


def render_text(items: list[ReportItem]) -> str:
    if not items:
        return "FinAI-BR\n\nNão há análises disponíveis."
    report_date = max(item.analysis_date for item in items)
    sections = [f"FinAI-BR — {_format_date(report_date)}", ""]
    for item in items:
        sections.extend([
            f"{item.ticker}: {_display_direction(item.sentiment)}",
            f"Horizonte: {item.time_horizon or 'incerto'}",
            f"Fechamento: R$ {_format_number(item.close)} ({_format_change(item.change_percent)})",
        ])
        sections.extend(f"{name}: {value}" for name, value in _historical_metrics(item))
        for title, lines in _item_sections(item):
            sections.append(f"{title}:")
            sections.extend(f"- {line}" for line in lines)
        if item.sources:
            sections.append("Fontes:")
            sections.extend(_format_source(source) for source in sorted(item.sources, key=lambda source: source.source_id))
        else:
            sections.append("Fontes: nenhuma fonte disponível")
        sections.append("")
    sections.append("Relatório informativo. Qualidade da evidência não representa probabilidade de retorno.")
    return "\n".join(sections).strip()


def render_html(items: list[ReportItem]) -> str:
    if not items:
        return "<p>Não há análises disponíveis.</p>"
    cards = []
    for item in items:
        metrics = [("Fechamento", "R$ " + _format_number(item.close)), ("Variação", _format_change(item.change_percent)), *_historical_metrics(item)]
        metric_rows = "".join(
            f'<tr><th style="text-align:left;padding:6px;border-bottom:1px solid #ddd">{html.escape(label)}</th>'
            f'<td style="padding:6px;border-bottom:1px solid #ddd">{html.escape(value)}</td></tr>'
            for label, value in metrics
        )
        content_sections = []
        for title, lines in _item_sections(item):
            body = "".join(f"<li>{html.escape(line)}</li>" for line in lines)
            content_sections.append(f"<h3>{html.escape(title)}</h3><ul>{body}</ul>")
        source_rows = []
        for source in sorted(item.sources, key=lambda value: value.source_id):
            title = html.escape((f"[{source.source_id}] " if source.source_id else "") + source.title)
            publisher = html.escape(source.publisher)
            date_text = html.escape(_format_date(source.published_at))
            safe_link = _safe_link(source.link)
            if safe_link:
                title = f'<a href="{html.escape(safe_link, quote=True)}">{title}</a>'
            source_rows.append(f"<li>{title}{' — ' + publisher if publisher else ''} — {date_text}</li>")
        sources = "".join(source_rows) or "<li>Nenhuma fonte disponível.</li>"
        cards.append(
            '<article style="background:#fff;border:1px solid #d6e1e2;border-radius:10px;padding:18px;margin:0 0 16px">'
            f'<h2 style="margin:0 0 12px">{html.escape(item.ticker)} — {html.escape(_display_direction(item.sentiment))}</h2>'
            f'<p>Horizonte: {html.escape(item.time_horizon or "incerto")}</p>'
            f'<table role="presentation" style="border-collapse:collapse;width:100%">{metric_rows}</table>'
            f'{"".join(content_sections)}<h3>Fontes</h3><ul>{sources}</ul></article>'
        )
    report_date = html.escape(_format_date(max(item.analysis_date for item in items)))
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    return template.replace("{{REPORT_DATE}}", report_date).replace("{{CARDS}}", "".join(cards))


def report_items_from_rows(rows: list[object]) -> list[ReportItem]:
    items = []
    for row in rows:
        analysis, asset, price = row.Analysis, row.Asset, row.Price
        source_rows = getattr(row, "sources", getattr(analysis, "sources", []))
        snapshot = {}
        context = None
        raw_snapshot = getattr(analysis, "market_context_json", None)
        if raw_snapshot:
            try:
                snapshot = json.loads(raw_snapshot)
                context = HistoricalContext.model_validate(snapshot["historical_context"])
            except (KeyError, TypeError, ValueError, ValidationError):
                snapshot, context = {}, None
        details = {}
        raw_details = getattr(analysis, "analysis_details_json", None)
        if raw_details:
            try:
                details = json.loads(raw_details)
                if not isinstance(details, dict) or details.get("version") != 1:
                    details = {}
            except (TypeError, ValueError):
                details = {}
        structured = details.get("analysis", {})
        evidence = details.get("research_evidence", [])
        source_metadata = {
            source.get("source_id"): source
            for source in details.get("source_metadata", [])
            if isinstance(source, dict) and isinstance(source.get("source_id"), int)
        }
        sources = []
        for source in source_rows:
            source_id = source.source_order
            metadata = source_metadata.get(source_id, {})
            sources.append(ReportSource(
                title=source.news.title, link=source.news.link,
                published_at=source.news.published_at, source_id=source_id,
                publisher=getattr(source.news, "publisher", None) or metadata.get("publisher", ""),
            ))
        detail_by_id = {source.source_id for source in sources}
        for source_id, metadata in source_metadata.items():
            if source_id not in detail_by_id:
                try:
                    published = datetime.fromisoformat(metadata["published_at"]) if metadata.get("published_at") else None
                except ValueError:
                    published = None
                sources.append(ReportSource(
                    title=metadata.get("title", "Fonte"), link=metadata.get("link", ""),
                    published_at=published, source_id=source_id, publisher=metadata.get("publisher", ""),
                ))
        confidence = analysis.confidence
        label, explanation = _quality(confidence, evidence) if details else (
            "legada", "Análise legada sem classificação de qualidade da evidência."
        )
        items.append(ReportItem(
            ticker=asset.ticker,
            analysis_date=analysis.analysis_date,
            sentiment=getattr(analysis, "direction", None) or analysis.sentiment,
            time_horizon=getattr(analysis, "time_horizon", None),
            confidence=confidence,
            rationale=analysis.rationale,
            risks=json.loads(getattr(analysis, "risks_json", "[]")),
            close=snapshot.get("close", price.close),
            change_percent=snapshot.get("change_percent", price.change_percent),
            sources=sorted(sources, key=lambda source: source.source_id),
            volume=snapshot.get("volume", getattr(price, "volume", None)),
            historical_context=context,
            summary=structured.get("summary", ""),
            catalysts=structured.get("catalysts", []),
            risk_details=structured.get("risk_details", []),
            forecasts=structured.get("forecasts", []),
            limitations=structured.get("limitations", details.get("limitations", [])),
            research_evidence=evidence,
            quality_label=label,
            quality_explanation=explanation,
        ))
    return items
