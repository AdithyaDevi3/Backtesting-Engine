import argparse
from datetime import date

import yfinance as yf
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.database import Base, SessionLocal, engine
from app.models import OHLCV


def ingest(ticker: str, start: date, end: date | None = None) -> int:
    ticker = ticker.upper()
    # Adjusted OHLC avoids artificial returns around splits and distributions.
    frame = yf.download(ticker, start=start.isoformat(), end=end.isoformat() if end else None, auto_adjust=True)
    if frame.empty:
        raise RuntimeError(f"No data returned for {ticker}")
    if getattr(frame.columns, "nlevels", 1) > 1:
        frame.columns = frame.columns.get_level_values(0)
    frame.columns = [str(column).lower() for column in frame.columns]

    Base.metadata.create_all(engine)
    records = []
    for timestamp, row in frame.iterrows():
        records.append(
            {
                "ticker": ticker,
                "date": timestamp.date(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume", 0)),
            }
        )
    with SessionLocal() as session:
        if engine.dialect.name == "sqlite":
            statement = sqlite_insert(OHLCV).values(records).on_conflict_do_nothing(
                index_elements=["ticker", "date"]
            )
            session.execute(statement)
        else:
            existing = {
                row.date for row in session.query(OHLCV).filter(OHLCV.ticker == ticker).all()
            }
            session.add_all(OHLCV(**record) for record in records if record["date"] not in existing)
        session.commit()
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and store historical OHLCV data")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat)
    args = parser.parse_args()
    count = ingest(args.ticker, args.start, args.end)
    print(f"Processed {count} rows for {args.ticker.upper()}")


if __name__ == "__main__":
    main()
