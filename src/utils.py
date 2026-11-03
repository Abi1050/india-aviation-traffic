"""Small shared helpers: formatting, quarter labels and logging."""

from __future__ import annotations

import logging
import math
import re
from typing import Iterable

import numpy as np
import pandas as pd

LOGGER_NAME = "aviation"


def get_logger(name: str = LOGGER_NAME) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def quarter_label(ts: pd.Timestamp | str) -> str:
    """``2026-04-01`` -> ``2026 Q2``."""
    ts = pd.Timestamp(ts)
    return f"{ts.year} Q{(ts.month - 1) // 3 + 1}"


def quarter_labels(index: Iterable) -> list[str]:
    return [quarter_label(ts) for ts in index]


def label_to_timestamp(label: str) -> pd.Timestamp:
    year, q = label.split(" Q")
    return pd.Timestamp(year=int(year), month=(int(q) - 1) * 3 + 1, day=1)


def quarter_end(ts: pd.Timestamp) -> pd.Timestamp:
    return (pd.Timestamp(ts).to_period("Q").end_time).normalize()


def is_finite_number(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def fmt_number(value, decimals: int = 0, compact: bool = False) -> str:
    """Readable number; returns an en dash for missing or non-finite values."""
    if not is_finite_number(value):
        return "–"
    value = float(value)
    if compact:
        for threshold, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
            if abs(value) >= threshold:
                return f"{value / threshold:,.2f}{suffix}"
    return f"{value:,.{decimals}f}"


def fmt_pct(value, decimals: int = 1, signed: bool = True) -> str:
    if not is_finite_number(value):
        return "–"
    return f"{float(value):+.{decimals}f}%" if signed else f"{float(value):.{decimals}f}%"


def safe_pct_change(current, previous) -> float:
    """Percentage change that returns NaN instead of dividing by zero or missing values."""
    if not (is_finite_number(current) and is_finite_number(previous)) or float(previous) == 0:
        return float("nan")
    return (float(current) - float(previous)) / abs(float(previous)) * 100.0


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def finite_or_nan(values) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    arr[~np.isfinite(arr)] = np.nan
    return arr
