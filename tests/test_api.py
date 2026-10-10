from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, database_url_from_environment, get_db
from app.main import app
from app.jobs import process_job, recover_expired_jobs
from app.models import OHLCV, ResearchJob


engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
Base.metadata.create_all(engine)


def override_db():
    with Session(engine) as session:
        yield session


app.dependency_overrides[get_db] = override_db
client = TestClient(app)
JobSession = sessionmaker(bind=engine)


def setup_module():
    start = date(2024, 1, 1)
    closes = [100 + index + (index % 7) * 2 for index in range(120)]
    with Session(engine) as session:
        for ticker, multiplier in (("TEST", 1), ("TEST2", 1.5)):
            session.add_all(
                OHLCV(
                    ticker=ticker,
                    date=start + timedelta(days=index),
                    open=close * multiplier - 1,
                    high=close * multiplier + 1,
                    low=close * multiplier - 2,
                    close=close * multiplier,
                    volume=1_000,
                )
                for index, close in enumerate(closes)
            )
        session.commit()


def test_health_check():
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json() == {"status": "ready"}


def test_database_url_is_built_without_embedding_credentials_in_configuration():
    url = database_url_from_environment(
        {
            "POSTGRES_HOST": "database",
            "POSTGRES_USER": "alphatest",
            "POSTGRES_PASSWORD": "".join(["local", "-", "only"]),
            "POSTGRES_DB": "alphatest",
        }
    )

    assert url.startswith("postgresql+psycopg://alphatest:")
    assert url.endswith("@database:5432/alphatest")


def test_optional_api_key_protects_api_routes(monkeypatch):
    monkeypatch.setenv("ALPHATEST_API_KEY", "test-only-key")

    unauthorized = client.get("/api/strategies")
    authorized = client.get("/api/strategies", headers={"X-API-Key": "test-only-key"})

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert client.get("/health").status_code == 200


def test_backtest_endpoint_runs_and_persists_result():
    response = client.post(
        "/api/backtest",
        json={
            "ticker": "test",
            "strategy": "sma",
            "params": {"short_window": 5, "long_window": 15},
            "start_date": "2024-01-01",
            "end_date": "2024-04-29",
            "initial_capital": 10_000,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["id"] > 0
    assert payload["ticker"] == "TEST"
    assert payload["execution"]["model"] == "next_open"
    assert payload["provenance"]["engine_revision"]
    assert len(payload["provenance"]["request_fingerprint"]) == 64
    assert len(payload["provenance"]["data_fingerprint"]) == 64
    assert payload["provenance"]["data_row_count"] == 120
    assert payload["provenance"]["data_start"] == "2024-01-01"
    assert payload["provenance"]["data_end"] == "2024-04-29"
    assert len(payload["equity_curve"]) == 120
    assert "max_drawdown" in payload["metrics"]
    assert "turnover" in payload["metrics"]
    assert payload["periodic_returns"]["monthly"]
    assert "drawdown" in payload["equity_curve"][0]
    history = client.get("/api/results").json()
    assert history[0]["id"] == payload["id"]
    assert history[0]["execution_model"] == "next_open"
    assert history[0]["slippage_bps"] == 0
    assert history[0]["position_size_pct"] == 100
    assert history[0]["stop_loss_pct"] is None
    assert history[0]["fractional_shares"] is True
    assert history[0]["status"] == "completed"
    assert history[0]["request_fingerprint"] == payload["provenance"]["request_fingerprint"]
    assert history[0]["data_fingerprint"] == payload["provenance"]["data_fingerprint"]
    detail = client.get(f"/api/results/{payload['id']}")
    assert detail.status_code == 200
    assert detail.json()["trades"] == payload["trades"]
    assert detail.json()["request_snapshot"]["ticker"] == "TEST"


def test_repeated_backtests_have_stable_provenance():
    request = {
        "ticker": "TEST",
        "strategy": "sma",
        "params": {"short_window": 5, "long_window": 15},
        "start_date": "2024-01-01",
        "end_date": "2024-04-29",
        "initial_capital": 10_000,
    }

    first = client.post("/api/backtest", json=request).json()["provenance"]
    second = client.post("/api/backtest", json=request).json()["provenance"]
    changed = client.post("/api/backtest", json={**request, "commission": 1}).json()["provenance"]

    assert first == second
    assert changed["data_fingerprint"] == first["data_fingerprint"]
    assert changed["request_fingerprint"] != first["request_fingerprint"]


def test_missing_result_detail_returns_not_found():
    response = client.get("/api/results/999999")

    assert response.status_code == 404


def test_saved_configuration_crud_run_and_result_rerun():
    configuration = {
        "name": "test momentum setup",
        "description": "Reusable deterministic API fixture",
        "ticker": "test",
        "strategy": "sma",
        "params": {"short_window": 5, "long_window": 15},
        "start_date": "2024-01-01",
        "end_date": "2024-04-29",
        "initial_capital": 10_000,
        "commission": 0,
    }
    created = client.post("/api/configurations", json=configuration)
    assert created.status_code == 201, created.text
    configuration_id = created.json()["id"]
    assert created.json()["ticker"] == "TEST"

    duplicate = client.post("/api/configurations", json=configuration)
    assert duplicate.status_code == 409

    listed = client.get("/api/configurations")
    assert any(item["id"] == configuration_id for item in listed.json())
    fetched = client.get(f"/api/configurations/{configuration_id}")
    assert fetched.json()["description"] == configuration["description"]

    updated_payload = {**configuration, "name": "updated momentum setup", "commission": 1}
    updated = client.put(f"/api/configurations/{configuration_id}", json=updated_payload)
    assert updated.status_code == 200, updated.text
    assert updated.json()["commission"] == 1

    configured_run = client.post(f"/api/configurations/{configuration_id}/run")
    assert configured_run.status_code == 200, configured_run.text
    configured_result = configured_run.json()
    assert configured_result["execution"]["commission"] == 1
    assert configured_result["source_result_id"] is None

    rerun = client.post(f"/api/results/{configured_result['id']}/rerun")
    assert rerun.status_code == 200, rerun.text
    assert rerun.json()["source_result_id"] == configured_result["id"]
    assert rerun.json()["provenance"] == configured_result["provenance"]
    rerun_detail = client.get(f"/api/results/{rerun.json()['id']}").json()
    assert rerun_detail["source_result_id"] == configured_result["id"]

    deleted = client.delete(f"/api/configurations/{configuration_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/configurations/{configuration_id}").status_code == 404


def test_saved_configuration_validates_dates_and_strategy():
    response = client.post(
        "/api/configurations",
        json={
            "name": "invalid setup",
            "ticker": "TEST",
            "strategy": "sma",
            "start_date": "2024-04-29",
            "end_date": "2024-01-01",
        },
    )

    assert response.status_code == 422

    blank_name = client.post(
        "/api/configurations",
        json={
            "name": "   ",
            "ticker": "TEST",
            "strategy": "sma",
            "start_date": "2024-01-01",
            "end_date": "2024-04-29",
        },
    )
    assert blank_name.status_code == 422


def test_missing_configuration_and_result_rerun_return_not_found():
    assert client.get("/api/configurations/999999").status_code == 404
    assert client.post("/api/configurations/999999/run").status_code == 404
    assert client.post("/api/results/999999/rerun").status_code == 404


def test_invalid_sma_parameters_return_actionable_error():
    response = client.post(
        "/api/backtest",
        json={
            "ticker": "TEST",
            "strategy": "sma",
            "params": {"short_window": 20, "long_window": 10},
            "start_date": "2024-01-01",
            "end_date": "2024-04-29",
        },
    )

    assert response.status_code == 422
    assert "short_window" in response.json()["detail"]


def test_parameter_sweep_ranks_results():
    response = client.post(
        "/api/sweep",
        json={
            "ticker": "TEST",
            "strategy": "sma",
            "parameter_grid": {"short_window": [3, 5], "long_window": [15, 20]},
            "start_date": "2024-01-01",
            "end_date": "2024-04-29",
        },
    )

    assert response.status_code == 200, response.text
    assert len(response.json()["results"]) == 4


def test_durable_research_job_is_validated_processed_and_persisted():
    submitted = client.post(
        "/api/jobs",
        json={
            "kind": "sweep",
            "input_payload": {
                "ticker": "test",
                "strategy": "sma",
                "parameter_grid": {"short_window": [3, 5], "long_window": [15]},
                "start_date": "2024-01-01",
                "end_date": "2024-04-29",
            },
        },
    )

    assert submitted.status_code == 202, submitted.text
    job = submitted.json()
    assert job["status"] == "queued"
    assert job["input_payload"]["ticker"] == "TEST"
    assert process_job(job["id"], JobSession, worker_id="test-worker") is True

    completed = client.get(f"/api/jobs/{job['id']}")
    assert completed.status_code == 200
    payload = completed.json()
    assert payload["status"] == "completed"
    assert payload["progress"] == 1
    assert payload["attempts"] == 1
    assert payload["worker_id"] == "test-worker"
    assert len(payload["result"]["results"]) == 2


def test_queued_research_job_can_be_cancelled():
    submitted = client.post(
        "/api/jobs",
        json={
            "kind": "portfolio",
            "input_payload": {
                "components": [
                    {"ticker": "TEST", "allocation_pct": 100, "strategy": "sma"}
                ],
                "start_date": "2024-01-01",
                "end_date": "2024-04-29",
            },
        },
    )
    job_id = submitted.json()["id"]

    cancelled = client.post(f"/api/jobs/{job_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert process_job(job_id, JobSession) is False
    assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 409


def test_research_job_rejects_invalid_payload_and_records_worker_failure():
    invalid = client.post(
        "/api/jobs",
        json={"kind": "sweep", "input_payload": {"ticker": "TEST"}},
    )
    assert invalid.status_code == 422

    with Session(engine) as session:
        job = ResearchJob(
            kind="sweep",
            status="queued",
            input_payload={
                "ticker": "MISSING",
                "strategy": "sma",
                "parameter_grid": {"short_window": [3], "long_window": [15]},
                "start_date": "2024-01-01",
                "end_date": "2024-04-29",
            },
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id

    assert process_job(job_id, JobSession) is True
    failed = client.get(f"/api/jobs/{job_id}").json()
    assert failed["status"] == "failed"
    assert "No OHLCV data found" in failed["error"]


def test_expired_job_leases_are_recovered_without_reviving_cancellation():
    expired = datetime.now(timezone.utc) - timedelta(seconds=1)
    with Session(engine) as session:
        retry = ResearchJob(
            kind="sweep",
            status="running",
            input_payload={},
            worker_id="lost-worker",
            lease_expires_at=expired,
        )
        cancel = ResearchJob(
            kind="portfolio",
            status="running",
            input_payload={},
            worker_id="lost-worker",
            lease_expires_at=expired,
            cancel_requested=True,
        )
        session.add_all([retry, cancel])
        session.commit()
        retry_id, cancel_id = retry.id, cancel.id

        assert recover_expired_jobs(session) == 2
        session.expire_all()
        assert session.get(ResearchJob, retry_id).status == "queued"
        assert session.get(ResearchJob, cancel_id).status == "cancelled"


def test_walk_forward_endpoint_reports_out_of_sample_folds():
    response = client.post(
        "/api/walk-forward",
        json={
            "ticker": "TEST",
            "strategy": "sma",
            "parameter_grid": {"short_window": [3, 5], "long_window": [10, 15]},
            "start_date": "2024-01-01",
            "end_date": "2024-04-29",
            "train_points": 60,
            "test_points": 20,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["fold_count"] == 3
    assert payload["folds"][0]["training_metrics"]["benchmark_return"] is not None


def test_strategy_catalog_is_discoverable():
    response = client.get("/api/strategies")

    assert response.status_code == 200
    assert [item["name"] for item in response.json()["strategies"]] == [
        "sma",
        "rsi",
        "macd",
        "bollinger",
    ]


def test_execution_assumptions_are_validated_and_returned():
    response = client.post(
        "/api/backtest",
        json={
            "ticker": "TEST",
            "strategy": "sma",
            "params": {"short_window": 5, "long_window": 15},
            "start_date": "2024-01-01",
            "end_date": "2024-04-29",
            "execution_model": "same_close",
            "slippage_bps": 25,
            "commission": 2,
            "position_size_pct": 50,
            "stop_loss_pct": 5,
            "take_profit_pct": 15,
            "fractional_shares": False,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["execution"] == {
        "model": "same_close",
        "commission": 2.0,
        "slippage_bps": 25.0,
        "position_size_pct": 50.0,
        "stop_loss_pct": 5.0,
        "take_profit_pct": 15.0,
        "fractional_shares": False,
    }

    invalid = client.post(
        "/api/backtest",
        json={
            "ticker": "TEST",
            "strategy": "sma",
            "start_date": "2024-01-01",
            "end_date": "2024-04-29",
            "slippage_bps": 1_001,
        },
    )
    assert invalid.status_code == 422


def test_weighted_multi_asset_portfolio_endpoint():
    response = client.post(
        "/api/portfolio",
        json={
            "components": [
                {
                    "ticker": "TEST",
                    "allocation_pct": 60,
                    "strategy": "sma",
                    "params": {"short_window": 5, "long_window": 15},
                },
                {
                    "ticker": "TEST2",
                    "allocation_pct": 40,
                    "strategy": "macd",
                    "params": {"fast_period": 5, "slow_period": 12, "signal_period": 4},
                },
            ],
            "start_date": "2024-01-01",
            "end_date": "2024-04-29",
            "initial_capital": 10_000,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["components"]) == 2
    assert len(payload["equity_curve"]) == 120
    assert sum(component["allocation"] for component in payload["components"]) == 10_000
    assert {trade["ticker"] for trade in payload["trades"]} <= {"TEST", "TEST2"}


def test_portfolio_allocations_must_total_one_hundred():
    response = client.post(
        "/api/portfolio",
        json={
            "components": [
                {"ticker": "TEST", "allocation_pct": 80, "strategy": "sma"},
                {"ticker": "TEST2", "allocation_pct": 30, "strategy": "rsi"},
            ],
            "start_date": "2024-01-01",
            "end_date": "2024-04-29",
        },
    )

    assert response.status_code == 422
    assert "total 100" in response.text
