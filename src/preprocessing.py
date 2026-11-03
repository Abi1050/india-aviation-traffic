"""Turn a raw CSV into validated record-level and quarterly datasets."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from config.settings import TRAFFIC_COLUMNS
from src import validation as v
from src.utils import quarter_label


@dataclass
class DatasetBundle:
    source: str
    filename: str
    fmt: str
    raw: pd.DataFrame
    records: pd.DataFrame                # one row per valid source record, with a Date column
    quarterly: pd.DataFrame              # Date index (QS-JAN), one row per quarter, full range
    quality: pd.DataFrame                # data-quality report
    excluded: pd.DataFrame               # raw rows that were excluded, with a Reason column
    latest: dict = field(default_factory=dict)
    loaded_at: str = ""

    @property
    def has_country(self) -> bool:
        return "Country" in self.records.columns

    @property
    def countries(self) -> list[str]:
        return sorted(self.records["Country"].dropna().unique().tolist()) if self.has_country else []


def quarter_start(years: pd.Series, quarters: pd.Series) -> pd.Series:
    """Quarter start dates from four-digit years and quarter numbers 1-4."""
    months = (quarters.astype(int) - 1) * 3 + 1
    return pd.to_datetime({"year": years.astype(int), "month": months, "day": 1})


def aggregate_quarterly(records: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    """Sum records per quarter exactly once and reindex to a regular quarterly range.

    Quarters without any record appear as rows of NaN so gaps stay visible.
    """
    columns = columns or TRAFFIC_COLUMNS
    if records.empty:
        return pd.DataFrame(columns=columns, index=pd.DatetimeIndex([], name="Date", freq="QS-JAN"))
    grouped = records.groupby("Date")[columns].sum(min_count=1).sort_index()
    full = pd.date_range(grouped.index.min(), grouped.index.max(), freq="QS-JAN", name="Date")
    return grouped.reindex(full)


def prepare_dataset(
    raw: pd.DataFrame,
    source: str,
    filename: str,
    monthly_coverage: dict | None = None,
    today: pd.Timestamp | None = None,
) -> DatasetBundle:
    log = v.QualityLog()
    df = v.normalise_columns(raw.copy())
    fmt = v.detect_format(df.columns)
    log.add("Schema", "Pass", v.FORMAT_DESCRIPTIONS[fmt], len(df), "Columns recognised")
    df["Source row"] = np.arange(1, len(df) + 1)
    excluded_parts: list[pd.DataFrame] = []

    def exclude(mask: pd.Series, reason: str) -> None:
        nonlocal df
        if mask.any():
            part = raw.iloc[(df.loc[mask, "Source row"] - 1).to_numpy()].copy()
            part.insert(0, "Source row", df.loc[mask, "Source row"].to_numpy())
            part["Reason"] = reason
            excluded_parts.append(part)
            df = df.loc[~mask].copy()

    # ---- dates
    if fmt in (v.FORMAT_COUNTRY, v.FORMAT_YEAR_QUARTER):
        years, converted, bad_year = v.normalise_years(df["Year"])
        quarters, bad_quarter = v.validate_quarters(df["Quarter"])
        if converted:
            log.add("Two-digit years", "Info",
                    "Years 0-99 interpreted as 2000-2099 (source uses 15 = 2015).",
                    converted, "Converted to four digits")
        log.add("Year values", "Fail" if bad_year.any() else "Pass",
                f"{int(bad_year.sum())} invalid year value(s).", int(bad_year.sum()),
                "Rows excluded" if bad_year.any() else "None")
        log.add("Quarter values", "Fail" if bad_quarter.any() else "Pass",
                f"{int(bad_quarter.sum())} value(s) outside 1-4.", int(bad_quarter.sum()),
                "Rows excluded" if bad_quarter.any() else "None")
        df["Year"], df["Quarter"] = years, quarters
        exclude(bad_year | bad_quarter, "Invalid year or quarter")
        df["Date"] = quarter_start(df["Year"], df["Quarter"]) if len(df) else pd.Series(dtype="datetime64[ns]")
    else:
        parsed = pd.to_datetime(df["Date"], errors="coerce")
        bad_date = parsed.isna()
        log.add("Date values", "Fail" if bad_date.any() else "Pass",
                f"{int(bad_date.sum())} unparseable date(s).", int(bad_date.sum()),
                "Rows excluded" if bad_date.any() else "None")
        df["Date"] = parsed
        exclude(bad_date, "Unparseable date")
        aligned = df["Date"].dt.to_period("Q").dt.start_time
        shifted = int((aligned != df["Date"]).sum())
        if shifted:
            log.add("Quarter alignment", "Warning",
                    "Dates not on a quarter start were moved to the start of their quarter.",
                    shifted, "Dates aligned")
        df["Date"] = aligned
        df["Year"] = df["Date"].dt.year
        df["Quarter"] = df["Date"].dt.quarter

    # ---- numeric traffic values
    df, bad_numeric = v.coerce_numeric(df, TRAFFIC_COLUMNS)
    n_bad = sum(bad_numeric.values())
    log.add("Numeric values", "Warning" if n_bad else "Pass",
            ", ".join(f"{c}: {n}" for c, n in bad_numeric.items() if n) or "All traffic values numeric.",
            n_bad, "Treated as missing" if n_bad else "None")

    missing = df[TRAFFIC_COLUMNS].isna().sum()
    log.add("Missing values", "Warning" if missing.sum() else "Pass",
            ", ".join(f"{c}: {n}" for c, n in missing.items() if n) or "No missing traffic values.",
            int(missing.sum()),
            "Kept; quarterly sums use available values" if missing.sum() else "None")

    negative = (df[TRAFFIC_COLUMNS] < 0).any(axis=1)
    log.add("Negative values", "Fail" if negative.any() else "Pass",
            f"{int(negative.sum())} record(s) with negative traffic.", int(negative.sum()),
            "Rows excluded" if negative.any() else "None")
    exclude(negative, "Negative traffic value")

    # ---- country spelling variants (e.g. "UNITED ARAB EMIRATES*" vs "UNITED ARAB EMIRATES")
    if fmt == v.FORMAT_COUNTRY:
        df["Country"] = df["Country"].astype(str).str.strip()
        mapping, kept_apart = v.country_variants(df)
        if mapping:
            changed = df["Country"].isin(list(mapping))
            log.add("Country name variants", "Info",
                    "; ".join(f"'{a}' → '{b}'" for a, b in mapping.items()), int(changed.sum()),
                    "Harmonised (variants never share a quarter)")
            df["Country"] = df["Country"].replace(mapping)
        if kept_apart:
            log.add("Country name variants (overlapping)", "Warning",
                    "; ".join(" / ".join(names) for names in kept_apart), 0,
                    "Kept separate because they report the same quarter")

    # ---- duplicates (first occurrence kept so nothing is counted twice)
    key = ["Date", "Country"] if fmt == v.FORMAT_COUNTRY else ["Date"]
    exact = df.duplicated(subset=key + TRAFFIC_COLUMNS, keep="first")
    log.add("Duplicate rows", "Warning" if exact.any() else "Pass",
            f"{int(exact.sum())} exact duplicate record(s).", int(exact.sum()),
            "Later copies excluded" if exact.any() else "None")
    exclude(exact, "Exact duplicate record")
    conflict = df.duplicated(subset=key, keep="first")
    label = "quarter-country" if fmt == v.FORMAT_COUNTRY else "quarter"
    log.add(f"Duplicate {label} keys", "Fail" if conflict.any() else "Pass",
            f"{int(conflict.sum())} record(s) repeat a {label} with different values.", int(conflict.sum()),
            "Later records excluded; first kept" if conflict.any() else "None")
    exclude(conflict, f"Conflicting duplicate {label}")

    cols = ["Date", "Year", "Quarter"] + (["Country"] if fmt == v.FORMAT_COUNTRY else []) + TRAFFIC_COLUMNS
    records = df[cols].sort_values(key).reset_index(drop=True)
    records["Year"] = records["Year"].astype(int)
    records["Quarter"] = records["Quarter"].astype(int)
    if "Country" in records.columns:
        records["Country"] = records["Country"].astype(str).str.strip()

    quarterly = aggregate_quarterly(records)
    gaps = v.missing_quarters(quarterly.dropna(how="all").index)
    log.add("Quarter coverage", "Warning" if gaps else "Pass",
            ("Missing: " + ", ".join(quarter_label(g) for g in gaps)) if gaps else
            f"{len(quarterly)} consecutive quarters, no gaps.",
            len(gaps), "Shown as gaps; models need a complete series" if gaps else "None")

    latest = v.latest_quarter_assessment(quarterly, records, monthly_coverage, today)
    log.add("Latest quarter", "Pass" if latest["complete"] else "Warning",
            f"{latest['label']}: " + " ".join(latest.get("concerns") or latest.get("evidence") or []),
            0, "None" if latest["complete"] else "Interpret latest quarter with caution")

    excluded = (pd.concat(excluded_parts, ignore_index=True) if excluded_parts
                else pd.DataFrame(columns=["Source row", *raw.columns, "Reason"]))
    return DatasetBundle(
        source=source, filename=filename, fmt=fmt, raw=raw, records=records,
        quarterly=quarterly, quality=log.to_frame(), excluded=excluded, latest=latest,
        loaded_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def filter_quarterly(
    bundle: DatasetBundle,
    countries: list[str] | None = None,
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Quarterly totals for the selected countries and date window.

    Country filtering happens on records before the single aggregation step,
    so country-level observations are never summed twice.
    """
    if bundle.has_country and countries:
        recs = bundle.records[bundle.records["Country"].isin(countries)]
        quarterly = aggregate_quarterly(recs)
    else:
        quarterly = bundle.quarterly.copy()
    if start is not None:
        quarterly = quarterly.loc[quarterly.index >= pd.Timestamp(start)]
    if end is not None:
        quarterly = quarterly.loc[quarterly.index <= pd.Timestamp(end)]
    if len(quarterly):
        quarterly = quarterly.asfreq("QS-JAN")
    return quarterly


def filter_records(bundle: DatasetBundle, countries=None, start=None, end=None) -> pd.DataFrame:
    recs = bundle.records
    if bundle.has_country and countries:
        recs = recs[recs["Country"].isin(countries)]
    if start is not None:
        recs = recs[recs["Date"] >= pd.Timestamp(start)]
    if end is not None:
        recs = recs[recs["Date"] <= pd.Timestamp(end)]
    return recs.reset_index(drop=True)


def model_ready(quarterly: pd.DataFrame, columns: list[str]) -> list[str]:
    """Return a list of problems that prevent model fitting (empty list = ready)."""
    problems = []
    for col in columns:
        if col not in quarterly.columns:
            problems.append(f"{col} is not available.")
            continue
        series = quarterly[col]
        if series.isna().any():
            gaps = ", ".join(quarter_label(i) for i in series.index[series.isna()][:6])
            problems.append(f"{col} has {int(series.isna().sum())} missing quarter(s) ({gaps}).")
        if not np.isfinite(series.dropna().to_numpy(dtype=float)).all():
            problems.append(f"{col} contains non-finite values.")
    return problems
