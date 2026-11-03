"""Schema detection and data-quality checks.

Nothing in this module drops data silently: every check returns the affected rows
so the preprocessing step can report what was excluded and why.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from config.settings import TRAFFIC_COLUMNS
from src.utils import quarter_end, quarter_label

FORMAT_COUNTRY = "country"          # Year, Quarter, Country, traffic columns
FORMAT_YEAR_QUARTER = "year_quarter"  # Year, Quarter, traffic columns (one row per quarter)
FORMAT_QUARTERLY = "quarterly"      # Date, traffic columns (one row per quarter)

FORMAT_DESCRIPTIONS = {
    FORMAT_COUNTRY: "Country-level records (Year, Quarter, Country + traffic columns)",
    FORMAT_YEAR_QUARTER: "Quarterly records (Year, Quarter + traffic columns)",
    FORMAT_QUARTERLY: "Aggregated quarterly records (Date + traffic columns)",
}

SCHEMA_HELP = (
    "Supported layouts:\n"
    "1. Country-level: Year, Quarter, Country, PaxToIndia, PaxFromIndia, FreightToIndia, FreightFromIndia\n"
    "2. Quarterly: Year, Quarter, PaxToIndia, PaxFromIndia, FreightToIndia, FreightFromIndia\n"
    "3. Aggregated: Date, PaxToIndia, PaxFromIndia, FreightToIndia, FreightFromIndia"
)


class SchemaError(ValueError):
    """Raised when a CSV does not match any supported layout."""


@dataclass
class QualityLog:
    """Collects data-quality findings as rows of a report table."""

    rows: list[dict] = field(default_factory=list)

    def add(self, check: str, status: str, details: str, rows_affected: int = 0, action: str = "None") -> None:
        self.rows.append(
            {"Check": check, "Status": status, "Details": details,
             "Rows affected": int(rows_affected), "Action": action}
        )

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=["Check", "Status", "Details", "Rows affected", "Action"])


def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace and match column names case-insensitively to the schema."""
    canonical = {c.lower(): c for c in TRAFFIC_COLUMNS + ["Year", "Quarter", "Country", "Date"]}
    renamed = {}
    for col in df.columns:
        key = str(col).strip().lower()
        if key in canonical:
            renamed[col] = canonical[key]
    return df.rename(columns=renamed)


def detect_format(columns) -> str:
    cols = set(columns)
    missing_traffic = [c for c in TRAFFIC_COLUMNS if c not in cols]
    if missing_traffic:
        raise SchemaError(
            f"Missing required traffic column(s): {', '.join(missing_traffic)}.\n\n{SCHEMA_HELP}"
        )
    if {"Year", "Quarter", "Country"} <= cols:
        return FORMAT_COUNTRY
    if {"Year", "Quarter"} <= cols:
        return FORMAT_YEAR_QUARTER
    if "Date" in cols:
        return FORMAT_QUARTERLY
    raise SchemaError(f"No date information found (need Date, or Year and Quarter).\n\n{SCHEMA_HELP}")


def normalise_years(values: pd.Series) -> tuple[pd.Series, int, pd.Series]:
    """Convert years to four digits.

    Rule (documented in the app): integer years 0-99 are interpreted as 2000-2099,
    because the source dataset uses two-digit years starting at ``15`` (2015).
    Four-digit years 1900-2100 are kept. Anything else is invalid.

    Returns ``(years, number_converted, invalid_mask)``.
    """
    numeric = pd.to_numeric(values, errors="coerce")
    whole = numeric.notna() & (numeric == np.floor(numeric))
    two_digit = whole & numeric.between(0, 99)
    four_digit = whole & numeric.between(1900, 2100)
    years = numeric.where(~two_digit, numeric + 2000)
    invalid = ~(two_digit | four_digit)
    years = years.where(~invalid).astype("Int64")
    return years, int(two_digit.sum()), invalid


def validate_quarters(values: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Quarters must be whole numbers 1-4. Accepts ``Q1``-style strings too."""
    text = values.astype("string").str.strip().str.upper().str.removeprefix("Q")
    numeric = pd.to_numeric(text, errors="coerce")
    valid = numeric.isin([1, 2, 3, 4])
    return numeric.where(valid).astype("Int64"), ~valid


def coerce_numeric(df: pd.DataFrame, columns: list[str]) -> tuple[pd.DataFrame, dict[str, int]]:
    """Convert traffic columns to floats; count entries that were present but not numeric."""
    out = df.copy()
    bad_counts = {}
    for col in columns:
        original = out[col]
        if original.dtype == object or pd.api.types.is_string_dtype(original):
            cleaned = original.astype("string").str.replace(",", "", regex=False).str.strip()
        else:
            cleaned = original
        converted = pd.to_numeric(cleaned, errors="coerce").astype(float)
        converted[~np.isfinite(converted)] = np.nan
        bad_counts[col] = int((converted.isna() & original.notna()).sum())
        out[col] = converted
    return out, bad_counts


def country_variants(df: pd.DataFrame) -> tuple[dict[str, str], list[list[str]]]:
    """Find country names that differ only by case, whitespace or a trailing ``*``.

    Returns ``(mapping, overlapping)``: variants that never report the same quarter
    are mapped to one cleaned name; variants that overlap are listed and left alone.
    """
    key = df["Country"].astype(str).str.strip().str.rstrip("*").str.strip().str.upper()
    mapping, overlapping = {}, []
    for k, names in df.groupby(key)["Country"].unique().items():
        if len(names) < 2:
            continue
        sub = df[key == k]
        if sub.groupby("Date")["Country"].nunique().max() > 1:
            overlapping.append(sorted(names))
            continue
        mapping.update({n: k for n in names if n != k})
    return mapping, overlapping


def missing_quarters(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    if len(index) == 0:
        return []
    full = pd.date_range(index.min(), index.max(), freq="QS-JAN")
    return [ts for ts in full if ts not in set(index)]


def latest_quarter_assessment(
    quarterly: pd.DataFrame,
    records: pd.DataFrame | None = None,
    monthly_coverage: dict | None = None,
    today: pd.Timestamp | None = None,
) -> dict:
    """Decide whether the most recent quarter looks like a complete observation.

    Evidence used (each listed in the returned ``evidence``):
    1. the quarter's calendar end date has passed;
    2. monthly coverage (month 3 reported) when the optional monthly carrier file exists;
    3. number of reporting countries versus the median of the previous four quarters;
    4. passengers to India versus the same quarter a year earlier.
    """
    today = pd.Timestamp.today().normalize() if today is None else pd.Timestamp(today)
    observed = quarterly.dropna(how="all")
    if observed.empty:
        return {"label": "–", "complete": False, "status": "Unknown", "evidence": ["No observations"]}
    last = observed.index.max()
    evidence, concerns = [], []

    if quarter_end(last) >= today:
        concerns.append(f"{quarter_label(last)} has not finished yet (ends {quarter_end(last).date()}).")
    else:
        evidence.append(f"Calendar quarter ended on {quarter_end(last).date()}.")

    if monthly_coverage:
        if monthly_coverage.get("months_reported", 0) >= 3:
            evidence.append("Monthly carrier file reports all three months of the quarter.")
        else:
            concerns.append(
                f"Monthly carrier file reports only {monthly_coverage.get('months_reported')} of 3 months."
            )

    if records is not None and "Country" in records.columns:
        counts = records.groupby("Date")["Country"].nunique().sort_index()
        if last in counts.index and len(counts) >= 5:
            prev = counts.loc[:last].iloc[-5:-1]
            ratio = counts.loc[last] / max(prev.median(), 1)
            msg = f"{counts.loc[last]} reporting countries vs median {prev.median():.0f} in the previous four quarters."
            (evidence if ratio >= 0.85 else concerns).append(msg)

    if "PaxToIndia" in observed.columns:
        year_ago = last - pd.DateOffset(years=1)
        if year_ago in observed.index and observed.loc[year_ago, "PaxToIndia"] > 0:
            ratio = observed.loc[last, "PaxToIndia"] / observed.loc[year_ago, "PaxToIndia"]
            msg = f"Passengers to India are {ratio:.0%} of the same quarter last year."
            (evidence if ratio >= 0.7 else concerns).append(msg)

    complete = not concerns
    return {
        "label": quarter_label(last),
        "date": last,
        "complete": complete,
        "status": "Complete" if complete else "Possibly incomplete",
        "evidence": evidence,
        "concerns": concerns,
    }
