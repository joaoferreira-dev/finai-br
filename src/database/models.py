from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    prices: Mapped[list["Price"]] = relationship(back_populates="asset")


class Price(Base):
    __tablename__ = "prices"
    __table_args__ = (UniqueConstraint("asset_id", "trading_date", name="uq_price_asset_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    trading_date: Mapped[date] = mapped_column(Date)
    close: Mapped[float] = mapped_column(Float)
    change_percent: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(Integer)
    asset: Mapped[Asset] = relationship(back_populates="prices")


class News(Base):
    __tablename__ = "news"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    title: Mapped[str] = mapped_column(Text)
    link: Mapped[str] = mapped_column(Text, unique=True)
    summary: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class Analysis(Base):
    __tablename__ = "analyses"
    __table_args__ = (UniqueConstraint("asset_id", "analysis_date", name="uq_analysis_asset_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    analysis_date: Mapped[date] = mapped_column(Date)
    sentiment: Mapped[str] = mapped_column(String(40))
    confidence: Mapped[int] = mapped_column(Integer)
    rationale: Mapped[str] = mapped_column(Text)
    risks_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    sources: Mapped[list["AnalysisNews"]] = relationship(back_populates="analysis", cascade="all, delete-orphan")


class AnalysisNews(Base):
    __tablename__ = "analysis_news"
    __table_args__ = (UniqueConstraint("analysis_id", "news_id", name="uq_analysis_news"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"))
    news_id: Mapped[int] = mapped_column(ForeignKey("news.id", ondelete="CASCADE"))
    source_order: Mapped[int] = mapped_column(Integer)
    analysis: Mapped[Analysis] = relationship(back_populates="sources")
    news: Mapped[News] = relationship()
