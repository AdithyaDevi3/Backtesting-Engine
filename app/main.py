from contextlib import asynccontextmanager
import hmac
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.database import DATABASE_URL, engine
from app.routers.backtest import router as backtest_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    migrate_database()
    yield


def migrate_database() -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    command.upgrade(config, "head")


app = FastAPI(
    title="AlphaTest API",
    version="1.0.0",
    description="Run reproducible SMA and RSI backtests against historical OHLCV data.",
    lifespan=lifespan,
)
app.include_router(backtest_router, prefix="/api")


@app.middleware("http")
async def require_api_key(request: Request, call_next):
    """Protect API routes when ALPHATEST_API_KEY is configured."""
    expected = os.getenv("ALPHATEST_API_KEY")
    if expected and request.url.path.startswith("/api/"):
        supplied = request.headers.get("X-API-Key", "")
        if not hmac.compare_digest(supplied, expected):
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})
    return await call_next(request)


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["operations"], response_model=None)
def readiness() -> JSONResponse | dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not ready"})
    return {"status": "ready"}
