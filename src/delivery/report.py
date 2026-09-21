import html
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class ReportSource:
    title: str
    link: str
    published_at: datetime | None = None


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
    change_percent: float
    sources: list[ReportSource]


TEMPLATE_PATH = Path(__file__).parent / "templates" / "report.html"


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


def _format_source(source: ReportSource) -> str:
    link = _safe_link(source.link)
    if not link:
        return f"- {source.title}"
    return f"- {source.title} ({link})"


def _display_direction(value: str) -> str:
    return {"alta": "Impacto positivo", "neutro": "Impacto neutro", "baixa": "Impacto negativo"}.get(value, value)


def render_text(items: list[ReportItem]) -> str:
    if not items:
        return "FinAI-BR\n\nNão há análises disponíveis."
    report_date = max(item.analysis_date for item in items)
    sections = [f"FinAI-BR — {_format_date(report_date)}", ""]
    for item in items:
        sections.extend([
            f"{item.ticker}: {_display_direction(item.sentiment)} ({item.confidence}%)",
            f"Horizonte: {item.time_horizon or 'incerto'}",
            f"Fechamento: R$ {_format_number(item.close)} ({_format_number(item.change_percent, signed=True)}%)",
            f"Análise: {item.rationale}",
        ])
        if item.risks:
            sections.append("Riscos: " + "; ".join(item.risks))
        if item.sources:
            sections.append("Fontes:")
            sections.extend(_format_source(source) for source in item.sources)
        else:
            sections.append("Fontes: nenhuma fonte citada pelo agente")
        sections.append("")
    return "\n".join(sections).strip()


def render_html(items: list[ReportItem]) -> str:
    if not items:
        return "<p>Não há análises disponíveis.</p>"
    cards = []
    for item in items:
        change_class = "positive" if item.change_percent >= 0 else "negative"
        risks = "".join(f"<li>{html.escape(risk)}</li>" for risk in item.risks)
        risks_section = f"<h3>Riscos</h3><ul>{risks}</ul>" if risks else ""
        sources = []
        for source in item.sources:
            safe_link = _safe_link(source.link)
            title = html.escape(source.title)
            published = html.escape(_format_date(source.published_at))
            if safe_link:
                sources.append(f'<li><a href="{html.escape(safe_link, quote=True)}">{title}</a><span>{published}</span></li>')
            else:
                sources.append(f"<li>{title}<span>{published}</span></li>")
        source_section = "".join(sources) or "<li>Nenhuma fonte citada pelo agente.</li>"
        cards.append(f"""
        <article class="card">
          <header class="card-header">
            <div class="header-metric asset"><span>Ativo</span><strong>{html.escape(item.ticker)}</strong></div>
            <div class="header-metric"><span>Impacto</span><strong>{html.escape(_display_direction(item.sentiment).replace("Impacto ", ""))}</strong></div>
            <div class="header-metric"><span>Confiança</span><strong>{item.confidence}%</strong></div>
            <div class="header-metric"><span>Horizonte</span><strong>{html.escape(item.time_horizon or "incerto")}</strong></div>
          </header>
          <section class="metrics" aria-label="Dados de mercado">
            <div class="market-metric"><span>Fechamento</span><strong>R$ {_format_number(item.close)}</strong></div>
            <div class="market-metric"><span>Variação</span><strong class="{change_class}">{_format_number(item.change_percent, signed=True)}%</strong></div>
          </section>
          <p class="rationale">{html.escape(item.rationale)}</p>
          {risks_section}
          <h3>Fontes</h3><ul class="sources">{source_section}</ul>
        </article>
        """)
    report_date = html.escape(_format_date(max(item.analysis_date for item in items)))
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    return template.replace("{{REPORT_DATE}}", report_date).replace("{{CARDS}}", "".join(cards))


def report_items_from_rows(rows: list[object]) -> list[ReportItem]:
    items = []
    for row in rows:
        analysis, asset, price = row.Analysis, row.Asset, row.Price
        source_rows = getattr(row, "sources", getattr(analysis, "sources", []))
        items.append(ReportItem(
            ticker=asset.ticker,
            analysis_date=analysis.analysis_date,
            sentiment=getattr(analysis, "direction", None) or analysis.sentiment,
            time_horizon=getattr(analysis, "time_horizon", None),
            confidence=analysis.confidence,
            rationale=analysis.rationale,
            risks=json.loads(getattr(analysis, "risks_json", "[]")),
            close=price.close,
            change_percent=price.change_percent,
            sources=[ReportSource(title=source.news.title, link=source.news.link, published_at=source.news.published_at) for source in sorted(source_rows, key=lambda value: value.source_order)],
        ))
    return items
