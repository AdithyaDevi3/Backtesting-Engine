from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


StrategyName = Literal["sma", "rsi", "macd", "bollinger"]
ExecutionModel = Literal["next_open", "same_close"]
ResearchJobKind = Literal["sweep", "walk_forward", "portfolio"]


class BacktestRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9.\-^=]+$")
    strategy: StrategyName
    params: dict = Field(default_factory=dict)
    start_date: date
    end_date: date
    initial_capital: float = Field(default=10_000, gt=0)
    commission: float = Field(default=0, ge=0)
    slippage_bps: float = Field(default=0, ge=0, le=1_000)
    execution_model: ExecutionModel = "next_open"
    position_size_pct: float = Field(default=100, gt=0, le=100)
    stop_loss_pct: float | None = Field(default=None, gt=0, lt=100)
    take_profit_pct: float | None = Field(default=None, gt=0)
    fractional_shares: bool = True

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        self.ticker = self.ticker.upper()
        return self


class StrategyConfig(BaseModel):
    strategy: StrategyName
    params: dict = Field(default_factory=dict)


class CompareRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9.\-^=]+$")
    strategies: list[StrategyConfig] = Field(min_length=1, max_length=10)
    start_date: date
    end_date: date
    initial_capital: float = Field(default=10_000, gt=0)
    commission: float = Field(default=0, ge=0)
    slippage_bps: float = Field(default=0, ge=0, le=1_000)
    execution_model: ExecutionModel = "next_open"
    position_size_pct: float = Field(default=100, gt=0, le=100)
    stop_loss_pct: float | None = Field(default=None, gt=0, lt=100)
    take_profit_pct: float | None = Field(default=None, gt=0)
    fractional_shares: bool = True

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        self.ticker = self.ticker.upper()
        return self


class SweepRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9.\-^=]+$")
    strategy: StrategyName
    parameter_grid: dict[str, list[int | float]]
    start_date: date
    end_date: date
    initial_capital: float = Field(default=10_000, gt=0)
    commission: float = Field(default=0, ge=0)
    slippage_bps: float = Field(default=0, ge=0, le=1_000)
    execution_model: ExecutionModel = "next_open"
    position_size_pct: float = Field(default=100, gt=0, le=100)
    stop_loss_pct: float | None = Field(default=None, gt=0, lt=100)
    take_profit_pct: float | None = Field(default=None, gt=0)
    fractional_shares: bool = True
    rank_by: Literal["sharpe", "total_return", "max_drawdown"] = "sharpe"

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        self.ticker = self.ticker.upper()
        return self


class WalkForwardRequest(SweepRequest):
    train_points: int = Field(default=252, ge=20, le=2_500)
    test_points: int = Field(default=63, ge=5, le=500)


class PortfolioComponent(BaseModel):
    ticker: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9.\-^=]+$")
    allocation_pct: float = Field(gt=0, le=100)
    strategy: StrategyName
    params: dict = Field(default_factory=dict)


class PortfolioRequest(BaseModel):
    components: list[PortfolioComponent] = Field(min_length=1, max_length=20)
    start_date: date
    end_date: date
    initial_capital: float = Field(default=10_000, gt=0)
    commission: float = Field(default=0, ge=0)
    slippage_bps: float = Field(default=0, ge=0, le=1_000)
    execution_model: ExecutionModel = "next_open"
    position_size_pct: float = Field(default=100, gt=0, le=100)
    stop_loss_pct: float | None = Field(default=None, gt=0, lt=100)
    take_profit_pct: float | None = Field(default=None, gt=0)
    fractional_shares: bool = True

    @model_validator(mode="after")
    def validate_portfolio(self):
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        total = sum(component.allocation_pct for component in self.components)
        if abs(total - 100) > 0.01:
            raise ValueError(f"component allocations must total 100; got {total:g}")
        for component in self.components:
            component.ticker = component.ticker.upper()
        return self


class BacktestSummary(BaseModel):
    id: int
    ticker: str
    strategy: str
    params: dict
    execution_model: str
    commission: float
    slippage_bps: float
    position_size_pct: float
    stop_loss_pct: float | None
    take_profit_pct: float | None
    fractional_shares: bool
    status: str
    request_fingerprint: str | None
    engine_revision: str | None
    data_fingerprint: str | None
    data_row_count: int | None
    data_start: date | None
    data_end: date | None
    source_result_id: int | None
    metrics: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class BacktestDetail(BacktestSummary):
    request_snapshot: dict | None
    trades: list[dict]


class SavedConfigurationCreate(BacktestRequest):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must contain non-whitespace characters")
        return value


class SavedConfigurationResponse(SavedConfigurationCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ResearchJobCreate(BaseModel):
    kind: ResearchJobKind
    input_payload: dict


class ResearchJobSummary(BaseModel):
    id: int
    kind: ResearchJobKind
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    error: str | None
    progress: float
    attempts: int
    cancel_requested: bool
    worker_id: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class ResearchJobResponse(ResearchJobSummary):
    input_payload: dict
    result: dict | None
