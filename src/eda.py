"""Exploratory statistics and automatically generated, data-driven observations."""

from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import seasonal_decompose

from config.settings import LABELS, UNITS
from src.utils import fmt_number, fmt_pct, quarter_label, safe_pct_change


def descriptive_statistics(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    rows = []
    for col in columns:
        s = df[col].dropna().astype(float)
        if s.empty:
            continue
        rows.append({
            "Variable": col, "Unit": UNITS.get(col, ""), "Count": int(s.count()),
            "Mean": s.mean(), "Median": s.median(), "Std. dev.": s.std(),
            "Min": s.min(), "Q1": s.quantile(0.25), "Q3": s.quantile(0.75), "Max": s.max(),
            "Skewness": s.skew(), "Kurtosis": s.kurt(),
            "CV (%)": s.std() / s.mean() * 100 if s.mean() else np.nan,
        })
    return pd.DataFrame(rows)


def growth_table(series: pd.Series) -> pd.DataFrame:
    """Quarter-over-quarter and year-over-year % change with zero-safe denominators."""
    s = series.astype(float)
    prev_q, prev_y = s.shift(1), s.shift(4)
    qoq = [safe_pct_change(c, p) for c, p in zip(s, prev_q)]
    yoy = [safe_pct_change(c, p) for c, p in zip(s, prev_y)]
    out = pd.DataFrame({"Value": s, "QoQ change (%)": qoq, "YoY change (%)": yoy}, index=s.index)
    # Flag growth computed against unusually small bases (e.g. pandemic quarters).
    median = s.median()
    out["Small base"] = (prev_y < 0.25 * median) | (prev_q < 0.25 * median)
    return out


def annual_summary(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    g = df[columns].groupby(df.index.year)
    out = g.sum(min_count=1)
    out.insert(0, "Quarters observed", g.count().iloc[:, 0])
    out.index.name = "Year"
    out["Complete year"] = out["Quarters observed"] == 4
    return out.reset_index()


def seasonal_profile(df: pd.DataFrame, column: str) -> pd.DataFrame:
    s = df[column].dropna()
    frame = pd.DataFrame({"Year": s.index.year, "Quarter": "Q" + s.index.quarter.astype(str), "Value": s.values})
    return frame


def correlation_matrix(df: pd.DataFrame, columns: list[str], method: str = "pearson") -> pd.DataFrame:
    return df[columns].astype(float).corr(method=method)


def decompose(series: pd.Series, period: int = 4, model: str = "additive"):
    """Classical decomposition. Raises ``ValueError`` with a readable reason."""
    s = series.astype(float)
    if s.isna().any():
        raise ValueError("The series has missing quarters; decomposition needs a complete, regular series.")
    if len(s) < 2 * period:
        raise ValueError(f"Need at least {2 * period} observations for period {period}; found {len(s)}.")
    if model == "multiplicative" and (s <= 0).any():
        raise ValueError("Multiplicative decomposition requires strictly positive values.")
    return seasonal_decompose(s, model=model, period=period)


def series_insights(df: pd.DataFrame, column: str) -> list[str]:
    """Plain statements computed from the data - no causal explanations."""
    s = df[column].dropna().astype(float)
    name = LABELS.get(column, column)
    if len(s) < 5:
        return [f"Not enough observations of {name} for automatic insights."]
    out = []
    first4, last4 = s.iloc[:4].mean(), s.iloc[-4:].mean()
    change = safe_pct_change(last4, first4)
    direction = "higher" if change > 0 else "lower"
    out.append(
        f"The average of the last four quarters ({quarter_label(s.index[-4])}–{quarter_label(s.index[-1])}) is "
        f"{fmt_pct(abs(change), signed=False)} {direction} than the first four quarters "
        f"({quarter_label(s.index[0])}–{quarter_label(s.index[3])})."
    )
    hi, lo = s.idxmax(), s.idxmin()
    out.append(f"Highest quarter: {quarter_label(hi)} ({fmt_number(s.max())}). "
               f"Lowest quarter: {quarter_label(lo)} ({fmt_number(s.min())}).")
    g = growth_table(s)
    qoq = g["QoQ change (%)"].dropna()
    if not qoq.empty:
        dmin, dmax = qoq.idxmin(), qoq.idxmax()
        out.append(f"Largest quarter-over-quarter decline: {fmt_pct(qoq.min())} in {quarter_label(dmin)}. "
                   f"Largest quarter-over-quarter increase: {fmt_pct(qoq.max())} in {quarter_label(dmax)}"
                   + (" (measured from a very small base)." if g.loc[dmax, "Small base"] else "."))
    yoy = g["YoY change (%)"].dropna()
    if not yoy.empty:
        out.append(f"Latest year-over-year change ({quarter_label(s.index[-1])} vs {quarter_label(s.index[-5])}): "
                   f"{fmt_pct(yoy.iloc[-1])}.")
    if len(s) >= 8:
        prof = s.groupby(s.index.quarter).mean()
        out.append(f"On average, Q{int(prof.idxmax())} is the highest quarter and Q{int(prof.idxmin())} the lowest "
                   f"(difference {fmt_pct(safe_pct_change(prof.max(), prof.min()), signed=False)}).")
    return out


def correlation_insights(corr: pd.DataFrame) -> list[str]:
    pairs = []
    cols = corr.columns.tolist()
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            pairs.append((a, b, corr.loc[a, b]))
    if not pairs:
        return []
    strongest = max(pairs, key=lambda p: abs(p[2]))
    weakest = min(pairs, key=lambda p: abs(p[2]))
    return [
        f"Strongest association: {LABELS[strongest[0]]} and {LABELS[strongest[1]]} (r = {strongest[2]:.2f}).",
        f"Weakest association: {LABELS[weakest[0]]} and {LABELS[weakest[1]]} (r = {weakest[2]:.2f}).",
        "Correlation measures linear association only and does not imply causation; shared trends "
        "(e.g. the 2020–2021 disruption and recovery) inflate correlations between trending series.",
    ]


def top_countries(records: pd.DataFrame, column: str, n: int = 15) -> pd.DataFrame:
    totals = records.groupby("Country")[column].sum().sort_values(ascending=False)
    share = totals / totals.sum() * 100 if totals.sum() else totals * np.nan
    return pd.DataFrame({"Country": totals.index, "Total": totals.values, "Share (%)": share.values}).head(n)
