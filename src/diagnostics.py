"""Stationarity tests, autocorrelation and residual diagnostics."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.tsa.stattools import acf, adfuller, pacf

TRANSFORMS = ["Level", "First difference", "Seasonal difference", "Log first difference"]


def transform_series(series: pd.Series, transform: str, period: int = 4) -> pd.Series:
    s = series.astype(float)
    if transform == "Level":
        return s
    if transform == "First difference":
        return s.diff().dropna()
    if transform == "Seasonal difference":
        return s.diff(period).dropna()
    if transform == "Log first difference":
        if (s <= 0).any():
            raise ValueError("Log transform needs strictly positive values.")
        return np.log(s).diff().dropna()
    raise ValueError(f"Unknown transform {transform}")


def adf_test(series: pd.Series, alpha: float = 0.05, regression: str = "c") -> dict:
    """Augmented Dickey-Fuller test. H0: the series has a unit root (non-stationary)."""
    s = series.dropna().astype(float)
    if len(s) < 10:
        raise ValueError(f"ADF needs at least 10 observations; found {len(s)}.")
    if np.isclose(s.std(), 0):
        raise ValueError("Series is constant.")
    stat, pvalue, lags, nobs, crit, _ = adfuller(s, autolag="AIC", regression=regression)
    reject = pvalue < alpha
    return {
        "ADF statistic": stat, "p-value": pvalue, "Lags used": int(lags), "Observations used": int(nobs),
        "Critical 1%": crit["1%"], "Critical 5%": crit["5%"], "Critical 10%": crit["10%"],
        "Conclusion": ("Reject unit root – consistent with stationarity" if reject
                       else "Cannot reject unit root – evidence of non-stationarity"),
        "Stationary": bool(reject),
    }


def adf_table(df: pd.DataFrame, columns: list[str], transforms: list[str], alpha: float = 0.05,
              period: int = 4, regression: str = "c") -> pd.DataFrame:
    rows = []
    for col in columns:
        for tr in transforms:
            row = {"Variable": col, "Transform": tr}
            try:
                row.update(adf_test(transform_series(df[col].dropna(), tr, period), alpha, regression))
            except ValueError as exc:
                row.update({"Conclusion": f"Not computed: {exc}", "Stationary": None})
            rows.append(row)
    return pd.DataFrame(rows)


def default_nlags(n: int) -> int:
    """Lag limit: about a quarter of the sample, at most 12, and below n/2 for PACF."""
    return int(max(1, min(12, n // 4 if n >= 20 else n // 2 - 1, n // 2 - 1)))


def acf_pacf(series: pd.Series, nlags: int | None = None, alpha: float = 0.05) -> pd.DataFrame:
    s = series.dropna().astype(float)
    n = len(s)
    if n < 8:
        raise ValueError(f"Need at least 8 observations for ACF/PACF; found {n}.")
    nlags = min(nlags or default_nlags(n), n // 2 - 1)
    acf_vals = acf(s, nlags=nlags, fft=False)
    pacf_vals = pacf(s, nlags=nlags, method="ywm")
    bound = stats.norm.ppf(1 - alpha / 2) / np.sqrt(n)
    return pd.DataFrame({"Lag": np.arange(nlags + 1), "ACF": acf_vals, "PACF": pacf_vals, "Bound": bound})


def ljung_box(residuals: pd.Series, lags: list[int] | None = None, model_df: int = 0) -> pd.DataFrame:
    r = pd.Series(residuals).dropna().astype(float)
    n = len(r)
    if n < 8:
        raise ValueError(f"Ljung-Box needs at least 8 residuals; found {n}.")
    lags = [lag for lag in (lags or [4, 8]) if lag < n - 1 and lag > model_df] or [max(1, min(4, n // 3))]
    out = acorr_ljungbox(r, lags=lags, model_df=model_df if model_df < min(lags) else 0)
    out = out.reset_index().rename(columns={"index": "Lag", "lb_stat": "Q statistic", "lb_pvalue": "p-value"})
    return out


def residual_summary(residuals: pd.Series) -> dict:
    r = pd.Series(residuals).dropna().astype(float)
    n = len(r)
    out = {"N": n, "Mean": r.mean() if n else np.nan, "Std. dev.": r.std() if n > 1 else np.nan,
           "Min": r.min() if n else np.nan, "Max": r.max() if n else np.nan,
           "Skewness": r.skew() if n > 2 else np.nan, "Excess kurtosis": r.kurt() if n > 3 else np.nan}
    if n >= 3:
        sw = stats.shapiro(r)
        out["Shapiro-Wilk p-value"] = sw.pvalue
    if n >= 8:
        jb = stats.jarque_bera(r)
        out["Jarque-Bera p-value"] = jb.pvalue
    if n > 1 and r.std() > 0:
        t = stats.ttest_1samp(r, 0.0)
        out["Mean = 0 t-test p-value"] = t.pvalue
    return out


def qq_points(residuals: pd.Series) -> pd.DataFrame:
    r = pd.Series(residuals).dropna().astype(float)
    (theoretical, ordered), (slope, intercept, _) = stats.probplot(r, dist="norm")
    return pd.DataFrame({"Theoretical": theoretical, "Sample": ordered,
                         "Line": slope * np.asarray(theoretical) + intercept})


SMALL_SAMPLE = 20


def small_sample_note(n: int) -> str | None:
    if n < SMALL_SAMPLE:
        return (f"Only {n} values are available. Normality and autocorrelation tests have low power at this size, "
                "so treat p-values as indicative rather than conclusive.")
    return None
