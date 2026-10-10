from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.data.loader import load_ohlcv
from app.database import get_db
from app.engine import (
    compute_metrics,
    periodic_returns,
    run_backtest,
)
from app.engine.strategies import get_strategy
from app.jobs import validate_job_input
from app.models import BacktestRecord, ResearchJob, SavedConfiguration
from app.provenance import build_provenance
from app.research import run_portfolio_research, run_sweep, run_walk_forward_research
from app.schemas import (
    BacktestRequest,
    BacktestDetail,
    BacktestSummary,
    CompareRequest,
    PortfolioRequest,
    ResearchJobCreate,
    ResearchJobResponse,
    ResearchJobSummary,
    SavedConfigurationCreate,
    SavedConfigurationResponse,
    SweepRequest,
    WalkForwardRequest,
)


router = APIRouter(tags=["backtests"])


@router.post("/backtest")
def create_backtest(request: BacktestRequest, db: Session = Depends(get_db)) -> dict:
    return _run_and_persist(db, request)


def _run_and_persist(
    db: Session, request: BacktestRequest, source_result_id: int | None = None
) -> dict:
    try:
        response = _execute(db, request)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    provenance = response["provenance"]
    request_snapshot = request.model_dump(mode="json")
    record = BacktestRecord(
        ticker=request.ticker,
        strategy=request.strategy,
        params=request.params,
        execution_model=request.execution_model,
        commission=request.commission,
        slippage_bps=request.slippage_bps,
        position_size_pct=request.position_size_pct,
        stop_loss_pct=request.stop_loss_pct,
        take_profit_pct=request.take_profit_pct,
        fractional_shares=request.fractional_shares,
        status="completed",
        request_snapshot=request_snapshot,
        request_fingerprint=provenance["request_fingerprint"],
        engine_revision=provenance["engine_revision"],
        data_fingerprint=provenance["data_fingerprint"],
        data_row_count=provenance["data_row_count"],
        data_start=date.fromisoformat(provenance["data_start"][:10]),
        data_end=date.fromisoformat(provenance["data_end"][:10]),
        source_result_id=source_result_id,
        metrics=response["metrics"],
        trades=response["trades"],
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    response["id"] = record.id
    response["source_result_id"] = source_result_id
    return response


@router.post("/compare")
def compare_strategies(request: CompareRequest, db: Session = Depends(get_db)) -> dict:
    results = []
    for configuration in request.strategies:
        try:
            backtest_request = BacktestRequest(
                ticker=request.ticker,
                strategy=configuration.strategy,
                params=configuration.params,
                start_date=request.start_date,
                end_date=request.end_date,
                initial_capital=request.initial_capital,
                commission=request.commission,
                slippage_bps=request.slippage_bps,
                execution_model=request.execution_model,
                position_size_pct=request.position_size_pct,
                stop_loss_pct=request.stop_loss_pct,
                take_profit_pct=request.take_profit_pct,
                fractional_shares=request.fractional_shares,
            )
            result = _execute(db, backtest_request)
        except (LookupError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        results.append({"strategy": backtest_request.strategy, "params": backtest_request.params, **result})
    return {"ticker": request.ticker.upper(), "results": results}


@router.post("/sweep")
def sweep_parameters(request: SweepRequest, db: Session = Depends(get_db)) -> dict:
    try:
        return run_sweep(db, request)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/walk-forward")
def walk_forward(request: WalkForwardRequest, db: Session = Depends(get_db)) -> dict:
    try:
        return run_walk_forward_research(db, request)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/portfolio")
def run_portfolio(request: PortfolioRequest, db: Session = Depends(get_db)) -> dict:
    try:
        return run_portfolio_research(db, request)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/strategies")
def list_strategies() -> dict:
    return {
        "strategies": [
            {
                "name": "sma",
                "description": "Long while the short moving average is above the long average.",
                "defaults": {"short_window": 20, "long_window": 50},
            },
            {
                "name": "rsi",
                "description": "Enter below the oversold threshold and exit above overbought.",
                "defaults": {"period": 14, "oversold": 30, "overbought": 70},
            },
            {
                "name": "macd",
                "description": "Long while the MACD histogram is positive.",
                "defaults": {"fast_period": 12, "slow_period": 26, "signal_period": 9},
            },
            {
                "name": "bollinger",
                "description": "Enter below the lower band and exit above the upper band.",
                "defaults": {"window": 20, "standard_deviations": 2},
            },
        ]
    }


@router.get("/results", response_model=list[BacktestSummary])
def list_results(
    limit: int = Query(default=25, ge=1, le=250), db: Session = Depends(get_db)
) -> list[BacktestRecord]:
    return list(db.scalars(select(BacktestRecord).order_by(desc(BacktestRecord.created_at)).limit(limit)))


@router.get("/results/{result_id}", response_model=BacktestDetail)
def get_result(result_id: int, db: Session = Depends(get_db)) -> BacktestRecord:
    record = db.get(BacktestRecord, result_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Backtest result not found")
    return record


@router.post(
    "/jobs",
    response_model=ResearchJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_research_job(
    request: ResearchJobCreate, db: Session = Depends(get_db)
) -> ResearchJob:
    try:
        validated = validate_job_input(request.kind, request.input_payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    job = ResearchJob(
        kind=request.kind,
        status="queued",
        input_payload=validated.model_dump(mode="json"),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.get("/jobs", response_model=list[ResearchJobSummary])
def list_research_jobs(
    limit: int = Query(default=25, ge=1, le=250), db: Session = Depends(get_db)
) -> list[ResearchJob]:
    return list(
        db.scalars(select(ResearchJob).order_by(desc(ResearchJob.created_at)).limit(limit))
    )


@router.get("/jobs/{job_id}", response_model=ResearchJobResponse)
def get_research_job(job_id: int, db: Session = Depends(get_db)) -> ResearchJob:
    job = db.get(ResearchJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Research job not found")
    return job


@router.post("/jobs/{job_id}/cancel", response_model=ResearchJobResponse)
def cancel_research_job(job_id: int, db: Session = Depends(get_db)) -> ResearchJob:
    job = db.get(ResearchJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Research job not found")
    if job.status in {"completed", "failed", "cancelled"}:
        raise HTTPException(status_code=409, detail=f"Job is already {job.status}")
    job.cancel_requested = True
    if job.status == "queued":
        job.status = "cancelled"
        job.finished_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return job


@router.post("/results/{result_id}/rerun")
def rerun_result(result_id: int, db: Session = Depends(get_db)) -> dict:
    record = db.get(BacktestRecord, result_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Backtest result not found")
    if not record.request_snapshot:
        raise HTTPException(
            status_code=409,
            detail="This result predates request snapshots and cannot be rerun automatically",
        )
    request = BacktestRequest.model_validate(record.request_snapshot)
    return _run_and_persist(db, request, source_result_id=record.id)


@router.post(
    "/configurations",
    response_model=SavedConfigurationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_configuration(
    request: SavedConfigurationCreate, db: Session = Depends(get_db)
) -> SavedConfiguration:
    configuration = SavedConfiguration(**request.model_dump())
    db.add(configuration)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Configuration name already exists") from exc
    db.refresh(configuration)
    return configuration


@router.get("/configurations", response_model=list[SavedConfigurationResponse])
def list_configurations(db: Session = Depends(get_db)) -> list[SavedConfiguration]:
    return list(db.scalars(select(SavedConfiguration).order_by(SavedConfiguration.name)))


@router.get("/configurations/{configuration_id}", response_model=SavedConfigurationResponse)
def get_configuration(
    configuration_id: int, db: Session = Depends(get_db)
) -> SavedConfiguration:
    return _get_configuration_or_404(db, configuration_id)


@router.put("/configurations/{configuration_id}", response_model=SavedConfigurationResponse)
def update_configuration(
    configuration_id: int,
    request: SavedConfigurationCreate,
    db: Session = Depends(get_db),
) -> SavedConfiguration:
    configuration = _get_configuration_or_404(db, configuration_id)
    for field, value in request.model_dump().items():
        setattr(configuration, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Configuration name already exists") from exc
    db.refresh(configuration)
    return configuration


@router.delete("/configurations/{configuration_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_configuration(
    configuration_id: int, db: Session = Depends(get_db)
) -> Response:
    configuration = _get_configuration_or_404(db, configuration_id)
    db.delete(configuration)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/configurations/{configuration_id}/run")
def run_configuration(configuration_id: int, db: Session = Depends(get_db)) -> dict:
    configuration = _get_configuration_or_404(db, configuration_id)
    request = BacktestRequest.model_validate(
        {
            field: getattr(configuration, field)
            for field in BacktestRequest.model_fields
        }
    )
    return _run_and_persist(db, request)


def _get_configuration_or_404(db: Session, configuration_id: int) -> SavedConfiguration:
    configuration = db.get(SavedConfiguration, configuration_id)
    if configuration is None:
        raise HTTPException(status_code=404, detail="Saved configuration not found")
    return configuration


def _execute(db: Session, request: BacktestRequest) -> dict:
    data = load_ohlcv(db, request.ticker, request.start_date, request.end_date)
    request_snapshot = request.model_dump(mode="json")
    provenance = build_provenance(data, request_snapshot)
    strategy = get_strategy(request.strategy, request.params)
    result = run_backtest(
        data,
        strategy,
        request.initial_capital,
        request.commission,
        request.slippage_bps,
        request.execution_model,
        request.position_size_pct,
        request.stop_loss_pct,
        request.take_profit_pct,
        request.fractional_shares,
    )
    metrics = compute_metrics(result.frame, result.trades, request.initial_capital)
    equity_curve = [
        {
            "date": timestamp.isoformat(),
            "close": round(float(row["close"]), 6),
            "equity": round(float(row["equity"]), 6),
            "drawdown": round(float(row["drawdown"]), 8),
        }
        for timestamp, row in result.frame.iterrows()
    ]
    return {
        "ticker": request.ticker,
        "strategy": request.strategy,
        "params": request.params,
        "execution": {
            "model": request.execution_model,
            "commission": request.commission,
            "slippage_bps": request.slippage_bps,
            "position_size_pct": request.position_size_pct,
            "stop_loss_pct": request.stop_loss_pct,
            "take_profit_pct": request.take_profit_pct,
            "fractional_shares": request.fractional_shares,
        },
        "provenance": provenance,
        "metrics": metrics,
        "periodic_returns": periodic_returns(result.frame),
        "equity_curve": equity_curve,
        "trades": result.trades,
    }
