import logging
from email.message import EmailMessage
import smtplib

from sqlalchemy import select

from database.models import Analysis, Asset, Price
from database.session import SessionLocal
from settings import get_settings

logger = logging.getLogger(__name__)


def send_latest_report() -> None:
    settings = get_settings()
    if not settings.email_enabled:
        logger.info("EMAIL_ENABLED=false; relatório não enviado")
        return
    with SessionLocal() as session:
        rows = session.execute(select(Analysis, Asset, Price).join(Asset, Analysis.asset_id == Asset.id).join(Price, (Price.asset_id == Asset.id) & (Price.trading_date == Analysis.analysis_date)).order_by(Analysis.analysis_date.desc())).all()
    if not rows:
        logger.warning("Não há análises para enviar")
        return
    latest = rows[0].Analysis.analysis_date
    lines = [f"FinAI-BR — {latest:%d/%m/%Y}", ""]
    for analysis, asset, price in rows:
        if analysis.analysis_date == latest:
            lines.extend([f"{asset.ticker}: {analysis.sentiment} ({analysis.confidence}%)", f"Fechamento: R$ {price.close:.2f} ({price.change_percent:+.2f}%)", analysis.rationale, ""])
    message = EmailMessage()
    message["Subject"], message["From"], message["To"] = f"FinAI-BR | {latest:%d/%m/%Y}", settings.email_from, settings.email_to
    message.set_content("\n".join(lines))
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
