import hashlib
import json
import os
from datetime import date, datetime
from math import isfinite
from typing import Any

import pandas as pd


ENGINE_REVISION = os.getenv("ALPHATEST_ENGINE_REVISION", "1.0.0")
OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


def canonical_json(value: Any) -> str:
    """Serialize JSON-compatible input consistently for hashing and storage."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
        default=_json_default,
    )


def fingerprint_request(snapshot: dict) -> str:
    return _sha256(canonical_json(snapshot).encode("utf-8"))


def fingerprint_ohlcv(frame: pd.DataFrame) -> str:
    """Hash normalized market inputs independently of their original row ordering."""
    missing = [column for column in OHLCV_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Cannot fingerprint OHLCV data missing columns: {', '.join(missing)}")
    if frame.index.has_duplicates:
        raise ValueError("Cannot fingerprint OHLCV data with duplicate timestamps")

    normalized = frame.loc[:, OHLCV_COLUMNS].sort_index()
    digest = hashlib.sha256()
    digest.update(b"alphatest-ohlcv-v1\n")
    for timestamp, row in normalized.iterrows():
        digest.update(_date_text(timestamp).encode("utf-8"))
        for column in OHLCV_COLUMNS:
            value = float(row[column])
            if not isfinite(value):
                raise ValueError(f"Cannot fingerprint non-finite {column} value")
            digest.update(b"\x1f")
            digest.update(format(value, ".17g").encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def build_provenance(frame: pd.DataFrame, request_snapshot: dict) -> dict:
    return {
        "engine_revision": ENGINE_REVISION,
        "request_fingerprint": fingerprint_request(request_snapshot),
        "data_fingerprint": fingerprint_ohlcv(frame),
        "data_row_count": len(frame),
        "data_start": _date_text(frame.index.min()),
        "data_end": _date_text(frame.index.max()),
    }


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _date_text(value: Any) -> str:
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
