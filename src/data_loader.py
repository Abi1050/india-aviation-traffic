"""Reading CSVs from the project folder, uploads and the optional remote source."""

from __future__ import annotations

import io
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

from config import settings
from src.preprocessing import DatasetBundle, prepare_dataset
from src.utils import get_logger

log = get_logger(__name__)

SOURCE_COUNTRY = "Local country-level source"
SOURCE_QUARTERLY = "Local quarterly aggregate"
SOURCE_UPLOAD = "Uploaded CSV"
SOURCE_REMOTE = "Remote repository refresh"


class DataLoadError(RuntimeError):
    pass


def read_csv_bytes(data: bytes, max_mb: float = settings.MAX_UPLOAD_MB) -> pd.DataFrame:
    """Parse CSV bytes as data only (nothing is executed)."""
    if len(data) > max_mb * 1024 * 1024:
        raise DataLoadError(f"File is larger than {max_mb:.0f} MB.")
    if not data.strip():
        raise DataLoadError("File is empty.")
    try:
        return pd.read_csv(io.BytesIO(data))
    except (pd.errors.ParserError, UnicodeDecodeError, ValueError) as exc:
        raise DataLoadError(f"Could not parse CSV: {exc}") from exc


def read_local_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise DataLoadError(f"File not found: {path}")
    return read_csv_bytes(path.read_bytes(), max_mb=500)


def monthly_coverage(path: Path = settings.CARRIER_MONTHLY_CSV) -> dict | None:
    """Months reported in the latest quarter of the optional monthly carrier file.

    ``carrier.csv`` holds month-1/2/3 passenger columns per quarter; if month 3 has
    traffic, the quarter covers all three months.
    """
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, usecols=["Year", "Quarter", "PaxToIndiaM1", "PaxToIndiaM2", "PaxToIndiaM3"])
    except (ValueError, pd.errors.ParserError) as exc:
        log.warning("Monthly coverage check skipped: %s", exc)
        return None
    df["Year"] = df["Year"].where(df["Year"] > 99, df["Year"] + 2000)
    last = df.sort_values(["Year", "Quarter"]).iloc[-1][["Year", "Quarter"]]
    sub = df[(df["Year"] == last["Year"]) & (df["Quarter"] == last["Quarter"])]
    months = sum(int(pd.to_numeric(sub[f"PaxToIndiaM{m}"], errors="coerce").fillna(0).sum() > 0) for m in (1, 2, 3))
    return {"year": int(last["Year"]), "quarter": int(last["Quarter"]), "months_reported": months}


def _coverage_for(bundle_quarterly_last: pd.Timestamp, coverage: dict | None) -> dict | None:
    if not coverage:
        return None
    if coverage["year"] == bundle_quarterly_last.year and coverage["quarter"] == bundle_quarterly_last.quarter:
        return coverage
    return None


def build_bundle(raw: pd.DataFrame, source: str, filename: str, use_monthly_check: bool) -> DatasetBundle:
    bundle = prepare_dataset(raw, source, filename)
    if use_monthly_check and not bundle.quarterly.dropna(how="all").empty:
        last = bundle.quarterly.dropna(how="all").index.max()
        cov = _coverage_for(last, monthly_coverage())
        if cov:
            bundle = prepare_dataset(raw, source, filename, monthly_coverage=cov)
    return bundle


def load_country_source(path: Path = settings.COUNTRY_CSV) -> DatasetBundle:
    return build_bundle(read_local_csv(path), SOURCE_COUNTRY, path.name, use_monthly_check=True)


def load_quarterly_aggregate(path: Path = settings.QUARTERLY_CSV) -> DatasetBundle:
    return build_bundle(read_local_csv(path), SOURCE_QUARTERLY, path.name, use_monthly_check=True)


def load_default() -> DatasetBundle:
    """Default priority: country-level source (supports country filters), then the
    notebook's quarterly aggregate. Remote data is only used on request."""
    errors = []
    for loader, path in ((load_country_source, settings.COUNTRY_CSV),
                         (load_quarterly_aggregate, settings.QUARTERLY_CSV)):
        if path.exists():
            try:
                return loader(path)
            except Exception as exc:  # noqa: BLE001 - try the next source, report all
                log.error("Failed to load %s: %s", path, exc)
                errors.append(f"{path.name}: {exc}")
        else:
            errors.append(f"{path} not found")
    raise DataLoadError("No usable local dataset. " + "; ".join(errors))


def load_upload(data: bytes, filename: str) -> DatasetBundle:
    return build_bundle(read_csv_bytes(data), SOURCE_UPLOAD, filename, use_monthly_check=False)


def fetch_remote(url: str = settings.REMOTE_COUNTRY_URL, timeout: int = settings.REMOTE_TIMEOUT_SECONDS) -> DatasetBundle:
    """Download the country-level CSV from the source repository (explicit user action only)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - fixed https URL
            data = response.read(settings.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise DataLoadError(f"Network request failed: {exc}") from exc
    return build_bundle(read_csv_bytes(data), SOURCE_REMOTE, url.rsplit("/", 1)[-1], use_monthly_check=False)
