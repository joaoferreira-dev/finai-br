from datetime import date, datetime, timezone

from delivery.report import ReportItem, ReportSource, render_html, render_text


def make_item() -> ReportItem:
    return ReportItem(
        ticker="VALE3",
        analysis_date=date(2026, 9, 18),
        sentiment="Moderado",
        time_horizon="incerto",
        confidence=70,
        rationale="Dados mistos e pressão recente no preço.",
        risks=["Volatilidade < elevada"],
        close=73.37,
        change_percent=-1.53,
        sources=[ReportSource("Notícia <principal>", "https://example.com/news", datetime(2026, 9, 18, tzinfo=timezone.utc))],
    )


def test_render_text_includes_analysis_and_sources() -> None:
    rendered = render_text([make_item()])

    assert "VALE3: Moderado" in rendered
    assert "Legada" in rendered
    assert "Confiança" not in rendered
    assert "Notícia <principal>" in rendered
    assert "https://example.com/news" in rendered
    assert "Volatilidade < elevada" in rendered


def test_render_html_escapes_content_and_keeps_valid_source_link() -> None:
    rendered = render_html([make_item()])

    assert "Notícia &lt;principal&gt;" in rendered
    assert "Volatilidade &lt; elevada" in rendered
    assert 'href="https://example.com/news"' in rendered
    assert "<script" not in rendered
    assert "Confiança" not in rendered


def test_render_html_does_not_link_unsafe_source() -> None:
    item = make_item()
    item = ReportItem(**{**item.__dict__, "sources": [ReportSource("Fonte", "javascript:alert(1)")]})

    rendered = render_html([item])

    assert "javascript:" not in rendered
    assert "Fonte" in rendered


def test_report_preserves_sparse_source_ids_and_replaces_unresolved_references() -> None:
    item = make_item()
    item = ReportItem(**{
        **item.__dict__,
        "rationale": "Projeção de retorno [4] e referência ausente [3].",
        "sources": [
            ReportSource("Fonte um", "https://example.com/1", source_id=1),
            ReportSource("Fonte quatro", "https://example.com/4", source_id=4),
        ],
    })

    rendered = render_text([item])

    assert "retorno [4]" in rendered
    assert "[referência indisponível: 3]" in rendered
    assert "[4] Fonte quatro" in rendered


def test_quality_is_capped_for_rss_and_marks_empty_evidence_insufficient() -> None:
    from delivery.report import _quality

    assert _quality(95, [{"uncertainties": []}])[0] == "limitada"
    assert _quality(95, [])[0] == "insuficiente"


def test_report_keeps_forecast_meaning_and_shows_related_sources() -> None:
    item = ReportItem(**{
        **make_item().__dict__,
        "summary": "Itaú estima dividend yield de dois dígitos [4].",
        "research_evidence": [{
            "source_id": 4, "related_source_ids": [2],
            "summary": "Estimativa de dividendo para 2027.", "uncertainties": ["condicionada ao Brent"],
        }],
        "forecasts": [{
            "broker": "Itaú BBA", "metric_type": "dividend yield", "value": "15%",
            "unit": "", "horizon": "2027", "assumptions": ["Brent a US$ 75"], "source_ids": [4],
        }],
        "sources": [
            ReportSource("Fonte dois", "https://example.com/2", source_id=2),
            ReportSource("Fonte quatro", "https://example.com/4", source_id=4),
        ],
        "quality_label": "limitada", "quality_explanation": "Somente trechos RSS.",
    })

    text = render_text([item])
    html = render_html([item])

    assert "dividend yield 15%" in text
    assert "Brent a US$ 75" in text
    assert "[2] Fonte dois" in text and "[4] Fonte quatro" in text
    assert "cobertura relacionada; não é confirmação independente" in text
    assert "dividend yield 15%" in html
