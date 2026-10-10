from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OHLCV(Base):
    __tablename__ = "ohlcv"
    __table_args__ = (
        UniqueConstraint("ticker", "date", name="uq_ohlcv_ticker_date"),
        Index("ix_ohlcv_lookup", "ticker", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    date: Mapped[date] = mapped_column(Date)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float, default=0)


class BacktestRecord(Base):
    __tablename__ = "backtest_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strategy: Mapped[str] = mapped_column(String(30), index=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    params: Mapped[dict] = mapped_column(JSON)
    execution_model: Mapped[str] = mapped_column(String(20), default="next_open")
    commission: Mapped[float] = mapped_column(Float, default=0)
    slippage_bps: Mapped[float] = mapped_column(Float, default=0)
    position_size_pct: Mapped[float] = mapped_column(Float, default=100)
    stop_loss_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    fractional_shares: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="completed", index=True)
    request_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    engine_revision: Mapped[str | None] = mapped_column(String(80), nullable=True)
    data_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data_row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_result_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON)
    trades: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )


class SavedConfiguration(Base):
    __tablename__ = "saved_configurations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    strategy: Mapped[str] = mapped_column(String(30), index=True)
    params: Mapped[dict] = mapped_column(JSON)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    initial_capital: Mapped[float] = mapped_column(Float, default=10_000)
    execution_model: Mapped[str] = mapped_column(String(20), default="next_open")
    commission: Mapped[float] = mapped_column(Float, default=0)
    slippage_bps: Mapped[float] = mapped_column(Float, default=0)
    position_size_pct: Mapped[float] = mapped_column(Float, default=100)
    stop_loss_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    fractional_shares: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ResearchJob(Base):
    __tablename__ = "research_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    input_payload: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress: Mapped[float] = mapped_column(Float, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    worker_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
