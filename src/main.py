import argparse
import json
import logging
from time import perf_counter
from zoneinfo import ZoneInfo

from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
    EVENT_JOB_MAX_INSTANCES,
    EVENT_JOB_MISSED,
    JobExecutionEvent,
    JobSubmissionEvent,
)
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from agents.market_workflow import MarketWorkflow
from database.models import Analysis, AnalysisNews, Asset, News, Price
from database.session import DEFAULT_ASSETS, SessionLocal, initialise_database
from delivery.email import send_latest_report
from ingestion.market_data import fetch_price
from ingestion.news import fetch_news
from settings import get_settings

logger = logging.getLogger(__name__)
SCHEDULER_TIMEZONE = ZoneInfo("America/Sao_Paulo")
SCHEDULER_MISFIRE_GRACE_SECONDS = 300


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
            market_snapshot = {
                "trading_date": price["trading_date"].isoformat(),
                "close": price["close"],
                "change_percent": price["change_percent"],
                "volume": price["volume"],
                "historical_context": price["historical_context"],
            }
            with SessionLocal() as session:
                existing_price = session.scalar(select(Price).where(Price.asset_id == asset.id, Price.trading_date == price["trading_date"]))
                if existing_price:
                    existing_price.close, existing_price.change_percent, existing_price.volume = price["close"], price["change_percent"], price["volume"]
                else:
                    session.add(Price(
                        asset_id=asset.id,
                        trading_date=price["trading_date"],
                        close=price["close"],
                        change_percent=price["change_percent"],
                        volume=price["volume"],
                    ))
                for item in news:
                    if item.link and not session.scalar(select(News).where(News.link == item.link)):
                        session.add(News(asset_id=asset.id, **item.model_dump()))
                existing = session.scalar(select(Analysis).where(Analysis.asset_id == asset.id, Analysis.analysis_date == price["trading_date"]))
                values = dict(sentiment=analysis.direction.value, direction=analysis.direction.value, time_horizon=analysis.time_horizon.value, confidence=analysis.confidence, rationale=analysis.rationale, risks_json=json.dumps(analysis.risks, ensure_ascii=False), market_context_json=json.dumps(market_snapshot, ensure_ascii=False, allow_nan=False))
                if existing:
                    for key, value in values.items():
                        setattr(existing, key, value)
                    existing.sources.clear()
                    analysis_record = existing
                else:
                    analysis_record = Analysis(asset_id=asset.id, analysis_date=price["trading_date"], **values)
                    session.add(analysis_record)
                session.flush()
                source_links = [news_item.link for index, news_item in enumerate(news, start=1) if index in analysis.source_ids and news_item.link]
                persisted_news = session.scalars(select(News).where(News.link.in_(source_links))).all() if source_links else []
                news_by_link = {item.link: item for item in persisted_news}
                analysis_record.sources.extend(
                    AnalysisNews(news_id=news_by_link[item.link].id, source_order=index)
                    for index, item in enumerate(news, start=1)
                    if index in analysis.source_ids and item.link in news_by_link
                )
                session.commit()
            logger.info("%s: persistência concluída", asset.ticker)
        except Exception:
            logger.exception("Falha ao processar %s; os demais ativos continuarão", asset.ticker)
    logger.info("Ciclo diário finalizado em %.1fs", perf_counter() - started_at)


def _log_scheduler_event(event: JobExecutionEvent | JobSubmissionEvent) -> None:
    if event.code == EVENT_JOB_MISSED:
        logger.error(
            "Job '%s' não executado: horário %s excedeu a tolerância de %ds",
            event.job_id,
            event.scheduled_run_time.astimezone(SCHEDULER_TIMEZONE).isoformat(),
            SCHEDULER_MISFIRE_GRACE_SECONDS,
        )
    elif event.code == EVENT_JOB_MAX_INSTANCES:
        logger.error("Job '%s' não executado: execução anterior ainda ativa", event.job_id)
    elif event.code == EVENT_JOB_ERROR:
        logger.error("Job '%s' finalizou com erro", event.job_id)
    elif event.code == EVENT_JOB_EXECUTED:
        logger.info("Job '%s' finalizou com sucesso", event.job_id)


def create_scheduler() -> BlockingScheduler:
    """Allow brief host delays while avoiding overlapping or duplicate runs."""
    scheduler = BlockingScheduler(
        timezone=SCHEDULER_TIMEZONE,
        job_defaults={
            "misfire_grace_time": SCHEDULER_MISFIRE_GRACE_SECONDS,
            "coalesce": True,
            "max_instances": 1,
        },
    )
    scheduler.add_listener(
        _log_scheduler_event,
        EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED | EVENT_JOB_MAX_INSTANCES,
    )
    for job_id, callback, hour in (
        ("daily-cycle", run_daily_cycle, 18),
        ("send-report", send_latest_report, 8),
    ):
        scheduler.add_job(
            callback,
            CronTrigger(day_of_week="mon-fri", hour=hour, minute=0, timezone=SCHEDULER_TIMEZONE),
            id=job_id,
        )
    return scheduler


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
        scheduler = create_scheduler()
        for job in scheduler.get_jobs():
            logger.info(
                "Job '%s' registrado com trigger %s; timezone=%s; tolerância=%ds",
                job.id, job.trigger, SCHEDULER_TIMEZONE, SCHEDULER_MISFIRE_GRACE_SECONDS,
            )
        if args.run_now:
            logger.info("Executando ciclo imediatamente (--run-now)")
            run_daily_cycle()
        logger.info("Scheduler iniciado; aguardando próximos horários")
        scheduler.start()


if __name__ == "__main__":
    main()
