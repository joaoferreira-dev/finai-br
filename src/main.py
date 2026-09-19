import argparse
import json
import logging
from time import perf_counter
from zoneinfo import ZoneInfo

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, JobExecutionEvent
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from agents.market_workflow import MarketWorkflow
from database.models import Analysis, Asset, News, Price
from database.session import DEFAULT_ASSETS, SessionLocal, initialise_database
from delivery.email import send_latest_report
from ingestion.market_data import fetch_price
from ingestion.news import fetch_news
from settings import get_settings

logger = logging.getLogger(__name__)


def run_daily_cycle() -> None:
    started_at = perf_counter()
    logger.info("Iniciando ciclo diário de coleta e análise")
    workflow = MarketWorkflow(get_settings())
    with SessionLocal() as session:
        assets = session.scalars(select(Asset).where(Asset.ticker.in_(DEFAULT_ASSETS))).all()
    logger.info("Total de ativos para processar: %d", len(assets))
    for asset in assets:
        try:
            logger.info("Coletando dados de %s", asset.ticker)
            price, news = fetch_price(asset.ticker), fetch_news(asset.ticker)
            logger.info("%s: preço coletado para %s e %d notícias", asset.ticker, price["trading_date"], len(news))
            analysis = workflow.invoke(asset.ticker, price, news)
            with SessionLocal() as session:
                existing_price = session.scalar(select(Price).where(Price.asset_id == asset.id, Price.trading_date == price["trading_date"]))
                if existing_price:
                    existing_price.close, existing_price.change_percent, existing_price.volume = price["close"], price["change_percent"], price["volume"]
                else:
                    session.add(Price(asset_id=asset.id, **price))
                for item in news:
                    if item.link and not session.scalar(select(News).where(News.link == item.link)):
                        session.add(News(asset_id=asset.id, **item.model_dump()))
                existing = session.scalar(select(Analysis).where(Analysis.asset_id == asset.id, Analysis.analysis_date == price["trading_date"]))
                values = dict(sentiment=analysis.sentiment.value, confidence=analysis.confidence, rationale=analysis.rationale, risks_json=json.dumps(analysis.risks, ensure_ascii=False))
                if existing:
                    for key, value in values.items():
                        setattr(existing, key, value)
                else:
                    session.add(Analysis(asset_id=asset.id, analysis_date=price["trading_date"], **values))
                session.commit()
            logger.info("%s: persistência concluída", asset.ticker)
        except Exception:
            logger.exception("Falha ao processar %s; os demais ativos continuarão", asset.ticker)
    logger.info("Ciclo diário finalizado em %.1fs", perf_counter() - started_at)


def _log_scheduler_event(event: JobExecutionEvent) -> None:
    if event.exception:
        logger.error("Job '%s' finalizou com erro", event.job_id)
    else:
        logger.info("Job '%s' finalizou com sucesso", event.job_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="FinAI-BR")
    parser.add_argument("command", choices=["run", "send-report", "scheduler"])
    parser.add_argument("--run-now", action="store_true", help="Executa um ciclo imediatamente antes de iniciar o scheduler")
    args = parser.parse_args()
    command = args.command
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    initialise_database()
    if command == "run":
        run_daily_cycle()
    elif command == "send-report":
        logger.info("Iniciando envio do relatório mais recente")
        send_latest_report()
        logger.info("Envio de relatório finalizado")
    else:
        scheduler = BlockingScheduler(timezone=ZoneInfo("America/Sao_Paulo"))
        scheduler.add_listener(_log_scheduler_event, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
        scheduler.add_job(run_daily_cycle, CronTrigger(day_of_week="mon-fri", hour=18, minute=0), id="daily-cycle")
        scheduler.add_job(send_latest_report, CronTrigger(day_of_week="mon-fri", hour=8, minute=0), id="send-report")
        for job in scheduler.get_jobs():
            logger.info("Job '%s' registrado com trigger %s", job.id, job.trigger)
        if args.run_now:
            logger.info("Executando ciclo imediatamente (--run-now)")
            run_daily_cycle()
        logger.info("Scheduler iniciado; aguardando próximos horários")
        scheduler.start()


if __name__ == "__main__":
    main()
