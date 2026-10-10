from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OHLCV


def load_ohlcv(session: Session, ticker: str, start_date: date, end_date: date) -> pd.DataFrame:
    ticker = ticker.upper()
    rows = session.scalars(
        select(OHLCV)
        .where(OHLCV.ticker == ticker, OHLCV.date >= start_date, OHLCV.date <= end_date)
        .order_by(OHLCV.date)
    ).all()
    if rows:
        return pd.DataFrame(
            [
                {
                    "date": row.date,
                    "open": row.open,
                    "high": row.high,
                    "low": row.low,
                    "close": row.close,
                    "volume": row.volume,
                }
                for row in rows
            ]
        ).set_index("date")

    # Existing repository CSVs provide a useful zero-setup fallback.
    for suffix in ("yahoo", "alpha"):
        path = Path("data/raw") / f"{ticker}_{suffix}.csv"
        if path.exists() and path.stat().st_size > 2:
            frame = _read_csv(path)
            frame = frame.loc[(frame.index.date >= start_date) & (frame.index.date <= end_date)]
            if not frame.empty:
                return frame
    raise LookupError(
        f"No OHLCV data found for {ticker} between {start_date} and {end_date}. "
        "Run `python -m app.data.ingest` first."
    )


def _read_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    # yfinance may emit two metadata rows when columns use a ticker MultiIndex.
    if "Price" in frame.columns:
        frame = pd.read_csv(path, skiprows=[1, 2])
        frame = frame.rename(columns={frame.columns[0]: "date"})
    else:
        frame = frame.rename(columns={frame.columns[0]: "date"})
    frame.columns = [str(column).strip().lower() for column in frame.columns]
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    for column in ("open", "high", "low", "close", "volume"):
        if column not in frame:
            frame[column] = 0.0
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["date", "close"]).set_index("date").sort_index()
