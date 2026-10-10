import argparse
import os
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import ResearchJob
from app.research import run_portfolio_research, run_sweep, run_walk_forward_research
from app.schemas import PortfolioRequest, SweepRequest, WalkForwardRequest


JobSessionFactory = Callable[[], Session]
LEASE_SECONDS = int(os.getenv("ALPHATEST_JOB_LEASE_SECONDS", "300"))


class JobCancelled(Exception):
    pass


class JobLeaseLost(Exception):
    pass


def validate_job_input(kind: str, payload: dict):
    schema = {
        "sweep": SweepRequest,
        "walk_forward": WalkForwardRequest,
        "portfolio": PortfolioRequest,
    }.get(kind)
    if schema is None:
        raise ValueError(f"Unsupported job kind: {kind}")
    return schema.model_validate(payload)


def execute_job_input(
    db: Session,
    kind: str,
    payload: dict,
    progress_callback: Callable[[float], None] | None = None,
) -> dict:
    request = validate_job_input(kind, payload)
    if kind == "sweep":
        return run_sweep(db, request, progress_callback)
    if kind == "walk_forward":
        return run_walk_forward_research(db, request, progress_callback)
    if kind == "portfolio":
        return run_portfolio_research(db, request, progress_callback)
    raise ValueError(f"Unsupported job kind: {kind}")


def recover_expired_jobs(db: Session) -> int:
    now = datetime.now(timezone.utc)
    cancelled = db.execute(
        update(ResearchJob)
        .where(
            ResearchJob.status == "running",
            ResearchJob.cancel_requested.is_(True),
            or_(ResearchJob.lease_expires_at.is_(None), ResearchJob.lease_expires_at < now),
        )
        .values(
            status="cancelled",
            worker_id=None,
            lease_expires_at=None,
            finished_at=now,
            error=None,
        )
        .execution_options(synchronize_session=False)
    )
    requeued = db.execute(
        update(ResearchJob)
        .where(
            ResearchJob.status == "running",
            ResearchJob.cancel_requested.is_(False),
            or_(ResearchJob.lease_expires_at.is_(None), ResearchJob.lease_expires_at < now),
        )
        .values(
            status="queued",
            worker_id=None,
            lease_expires_at=None,
            error="Worker lease expired; job was requeued",
        )
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return cancelled.rowcount + requeued.rowcount


def process_job(
    job_id: int,
    session_factory: JobSessionFactory = SessionLocal,
    worker_id: str | None = None,
) -> bool:
    worker_id = worker_id or f"worker-{uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        claimed = db.execute(
            update(ResearchJob)
            .where(ResearchJob.id == job_id, ResearchJob.status == "queued")
            .values(
                status="running",
                worker_id=worker_id,
                started_at=now,
                finished_at=None,
                lease_expires_at=now + timedelta(seconds=LEASE_SECONDS),
                attempts=ResearchJob.attempts + 1,
                error=None,
            )
            .execution_options(synchronize_session=False)
        )
        db.commit()
        if claimed.rowcount != 1:
            return False

        job = db.get(ResearchJob, job_id)
        if job is None:
            return False

        def report_progress(value: float) -> None:
            db.refresh(job, attribute_names=["cancel_requested", "status", "worker_id"])
            if job.status != "running" or job.worker_id != worker_id:
                raise JobLeaseLost
            if job.cancel_requested:
                raise JobCancelled
            job.progress = min(max(float(value), 0.0), 1.0)
            job.lease_expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=LEASE_SECONDS
            )
            db.commit()

        try:
            report_progress(0)
            result = execute_job_input(
                db, job.kind, job.input_payload, progress_callback=report_progress
            )
            report_progress(1)
        except JobLeaseLost:
            db.rollback()
            return False
        except JobCancelled:
            job.status = "cancelled"
            job.error = None
            job.finished_at = datetime.now(timezone.utc)
        except Exception as exc:
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {exc}"[:2_000]
            job.finished_at = datetime.now(timezone.utc)
        else:
            job.status = "completed"
            job.result = result
            job.error = None
            job.progress = 1.0
            job.finished_at = datetime.now(timezone.utc)
        job.lease_expires_at = None
        db.commit()
        return True


def process_next_job(
    session_factory: JobSessionFactory = SessionLocal,
    worker_id: str | None = None,
) -> bool:
    with session_factory() as db:
        recover_expired_jobs(db)
        job_id = db.scalar(
            select(ResearchJob.id)
            .where(ResearchJob.status == "queued")
            .order_by(ResearchJob.created_at, ResearchJob.id)
            .limit(1)
        )
    return bool(job_id and process_job(job_id, session_factory, worker_id))


def run_worker(poll_seconds: float) -> None:
    worker_id = f"worker-{uuid4().hex[:12]}"
    while True:
        if not process_next_job(SessionLocal, worker_id):
            time.sleep(poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the AlphaTest durable research worker")
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=float(os.getenv("ALPHATEST_JOB_POLL_SECONDS", "1")),
    )
    args = parser.parse_args()
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be positive")
    try:
        run_worker(args.poll_seconds)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
