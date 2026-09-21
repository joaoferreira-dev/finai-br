from datetime import date, datetime, timezone

from delivery.report import ReportItem, ReportSource, render_html, render_text


def make_item() -> ReportItem:
    return ReportItem(
        ticker="VALE3",
        analysis_date=date(2026, 9, 18),
        sentiment="Moderado",
        confidence=70,
        rationale="Dados mistos e pressão recente no preço.",
        risks=["Volatilidade < elevada"],
        close=73.37,
        change_percent=-1.53,
        sources=[ReportSource("Notícia <principal>", "https://example.com/news", datetime(2026, 9, 18, tzinfo=timezone.utc))],
    )


def test_render_text_includes_analysis_and_sources() -> None:
    rendered = render_text([make_item()])

    assert "VALE3: Moderado (70%)" in rendered
    assert "Notícia <principal> (https://example.com/news)" in rendered
    assert "Volatilidade < elevada" in rendered


def test_render_html_escapes_content_and_keeps_valid_source_link() -> None:
    rendered = render_html([make_item()])

    assert "Notícia &lt;principal&gt;" in rendered
    assert "Volatilidade &lt; elevada" in rendered
    assert 'href="https://example.com/news"' in rendered
    assert "<script" not in rendered


def test_render_html_does_not_link_unsafe_source() -> None:
    item = make_item()
    item = ReportItem(**{**item.__dict__, "sources": [ReportSource("Fonte", "javascript:alert(1)")]})

    rendered = render_html([item])

    assert "javascript:" not in rendered
    assert "Fonte" in rendered
