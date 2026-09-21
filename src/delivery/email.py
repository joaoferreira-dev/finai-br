import logging
from email.message import EmailMessage
import smtplib

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database.models import Analysis, Asset, Price
from database.models import AnalysisNews
from database.session import SessionLocal
from delivery.report import render_html, render_text, report_items_from_rows
from settings import get_settings

logger = logging.getLogger(__name__)


def send_latest_report() -> None:
    settings = get_settings()
    if not settings.email_enabled:
        logger.info("EMAIL_ENABLED=false; relatório não enviado")
        return
    with SessionLocal() as session:
        query = (
            select(Analysis, Asset, Price)
            .join(Asset, Analysis.asset_id == Asset.id)
            .join(Price, (Price.asset_id == Asset.id) & (Price.trading_date == Analysis.analysis_date))
            .options(selectinload(Analysis.sources).selectinload(AnalysisNews.news))
            .order_by(Analysis.analysis_date.desc(), Asset.ticker)
        )
        rows = session.execute(query).all()
    if not rows:
        logger.warning("Não há análises para enviar")
        return
    latest = rows[0].Analysis.analysis_date
    latest_rows = [row for row in rows if row.Analysis.analysis_date == latest]
    items = report_items_from_rows(latest_rows)
    message = EmailMessage()
    message["Subject"], message["From"], message["To"] = f"FinAI-BR | {latest:%d/%m/%Y}", settings.email_from, settings.email_to
    message.set_content(render_text(items))
    message.add_alternative(render_html(items), subtype="html")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
