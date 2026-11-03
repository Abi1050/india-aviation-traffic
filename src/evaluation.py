"""Forecast-error metrics and expanding-window rolling-origin evaluation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src import forecasting as fc
from src.utils import get_logger, quarter_label

log = get_logger(__name__)


# --------------------------------------------------------------------------- metrics
def _arrays(actual, predicted):
    a = np.asarray(actual, dtype=float)
    p = np.asarray(predicted, dtype=float)
    if a.shape != p.shape:
        raise ValueError("Actual and predicted values must have the same length.")
    mask = np.isfinite(a) & np.isfinite(p)
    return a[mask], p[mask]


def mae(actual, predicted) -> float:
    a, p = _arrays(actual, predicted)
    return float(np.mean(np.abs(a - p))) if len(a) else float("nan")


def rmse(actual, predicted) -> float:
    a, p = _arrays(actual, predicted)
    return float(np.sqrt(np.mean((a - p) ** 2))) if len(a) else float("nan")


def mape(actual, predicted) -> tuple[float, int]:
    """Mean absolute percentage error over non-zero actuals. Returns (value, n_used)."""
    a, p = _arrays(actual, predicted)
    nonzero = a != 0
    if not nonzero.any():
        return float("nan"), 0
    return float(np.mean(np.abs((a[nonzero] - p[nonzero]) / a[nonzero])) * 100), int(nonzero.sum())


def smape(actual, predicted) -> float:
    """Symmetric MAPE (0-200%); pairs where both values are zero are skipped."""
    a, p = _arrays(actual, predicted)
    denom = np.abs(a) + np.abs(p)
    ok = denom != 0
    return float(np.mean(2 * np.abs(a[ok] - p[ok]) / denom[ok]) * 100) if ok.any() else float("nan")


def compute_metrics(actual, predicted) -> dict:
    a, p = _arrays(actual, predicted)
    m, n_mape = mape(a, p)
    return {"N": len(a), "MAE": mae(a, p), "RMSE": rmse(a, p), "MAPE (%)": m, "MAPE N": n_mape,
            "sMAPE (%)": smape(a, p), "Bias (mean error)": float(np.mean(a - p)) if len(a) else float("nan")}


METRICS = ["MAE", "RMSE", "MAPE (%)", "sMAPE (%)"]


# --------------------------------------------------------------------------- rolling origin
def min_train_required(models: list[str], period: int, sarimax_cfg: fc.SarimaxConfig,
                       var_cfg: fc.VarConfig, n_series: int = 4) -> int:
    need = [period + 1]
    for m in models:
        if m == fc.NAIVE:
            need.append(period + 1)
        elif m == fc.SARIMAX:
            need.append(fc.sarimax_min_obs(sarimax_cfg))
        elif m in (fc.EXOG_CONDITIONAL, fc.EXOG_OPERATIONAL):
            need.append(fc.sarimax_min_obs(sarimax_cfg, n_series - 1))
        elif m == fc.VAR_MODEL:
            k = len(var_cfg.variables)
            need.append(fc.OBS_PER_COEF * (k + 1 + (3 if var_cfg.seasonal_dummies else 0)) + 2)
    return max(need)


def _one_step(model: str, train: pd.DataFrame, next_row: pd.DataFrame, target: str, period: int,
              sarimax_cfg: fc.SarimaxConfig, var_cfg: fc.VarConfig) -> float:
    y = train[target].rename(target)
    if model == fc.NAIVE:
        return fc.seasonal_naive_one_step(y, period)
    if model == fc.SARIMAX:
        return fc.sarimax_one_step(y, sarimax_cfg)
    exog_cols = fc.exog_columns_for(target)
    if model == fc.EXOG_CONDITIONAL:
        # Uses the *observed* regressors of the evaluation quarter: known-future scenario.
        return fc.sarimax_one_step(y, sarimax_cfg, train[exog_cols], next_row[exog_cols])
    if model == fc.EXOG_OPERATIONAL:
        # Regressors projected from information available at the origin only.
        projected = fc.project_exog(train[exog_cols], 1, period)
        return fc.sarimax_one_step(y, sarimax_cfg, train[exog_cols], projected)
    if model == fc.VAR_MODEL:
        return fc.var_one_step(train, target, var_cfg)
    raise fc.ForecastError(f"Unknown model {model}")


def rolling_origin(data: pd.DataFrame, target: str, models: list[str], test_size: int, period: int,
                   sarimax_cfg: fc.SarimaxConfig, var_cfg: fc.VarConfig, progress=None) -> dict:
    """Expanding-window one-step-ahead evaluation.

    For each evaluation quarter t the models are fitted on observations strictly
    before t, forecast t, and the window then grows by one quarter. All models
    share the same evaluation quarters; metrics use the quarters where every model
    produced a forecast.
    """
    if not models:
        raise ValueError("Select at least one model.")
    needed_cols = {target} | set(fc.exog_columns_for(target)) | set(var_cfg.variables)
    data = data[[c for c in data.columns if c in needed_cols]].astype(float)
    if data.isna().any().any():
        raise ValueError("The data contain missing quarters; rolling evaluation needs a complete series.")
    n = len(data)
    if test_size < 1 or test_size >= n:
        raise ValueError(f"Evaluation size must be between 1 and {n - 1}.")
    start = n - test_size
    need = min_train_required(models, period, sarimax_cfg, var_cfg, len(fc.exog_columns_for(target)) + 1)
    if start < need:
        raise ValueError(f"The first training window has {start} quarters but the selected models need at least "
                         f"{need}. Reduce the evaluation size or simplify the models.")
    rows, failures = [], []
    total = test_size * len(models)
    done = 0
    for i in range(start, n):
        date = data.index[i]
        train = data.iloc[:i]
        # Leakage guard: training data must end strictly before the forecast quarter.
        assert train.index.max() < date, "training window overlaps the evaluation quarter"
        row = {"Date": date, "Train end": train.index.max(), "Train size": len(train),
               "Actual": float(data[target].iloc[i])}
        for m in models:
            try:
                row[m] = _one_step(m, train, data.iloc[[i]], target, period, sarimax_cfg, var_cfg)
            except (fc.ForecastError, ValueError, np.linalg.LinAlgError) as exc:
                row[m] = np.nan
                failures.append({"Date": quarter_label(date), "Model": m, "Error": str(exc)})
                log.warning("Rolling forecast failed for %s at %s: %s", m, quarter_label(date), exc)
            done += 1
            if progress:
                progress(done / total, f"{m}: {quarter_label(date)}")
        rows.append(row)
    forecasts = pd.DataFrame(rows).set_index("Date")
    valid = [m for m in models if forecasts[m].notna().any()]
    common = forecasts[valid].notna().all(axis=1) if valid else pd.Series(False, index=forecasts.index)
    metrics_rows = []
    for m in valid:
        sub = forecasts.loc[common]
        metrics_rows.append({"Model": m, **compute_metrics(sub["Actual"], sub[m]),
                             "Failed origins": int(forecasts[m].isna().sum())})
    metrics = pd.DataFrame(metrics_rows)
    errors = []
    for m in valid:
        sub = forecasts.loc[common]
        e = sub["Actual"] - sub[m]
        errors.append(pd.DataFrame({"Date": sub.index, "Model": m, "Actual": sub["Actual"].values,
                                    "Predicted": sub[m].values, "Error": e.values,
                                    "Absolute error": e.abs().values,
                                    "APE (%)": (e.abs() / sub["Actual"].replace(0, np.nan) * 100).values}))
    errors = pd.concat(errors, ignore_index=True) if errors else pd.DataFrame()
    common_dates = forecasts.index[common]
    return {
        "forecasts": forecasts, "metrics": metrics, "errors": errors, "failures": pd.DataFrame(failures),
        "models": valid, "target": target, "test_size": test_size,
        "period_label": (f"{quarter_label(common_dates.min())} – {quarter_label(common_dates.max())}"
                         if len(common_dates) else "–"),
        "n_common": int(common.sum()), "first_train_size": start,
    }


def best_model(metrics: pd.DataFrame, metric: str = "MAE", candidates: list[str] | None = None) -> str | None:
    if metrics is None or metrics.empty or metric not in metrics:
        return None
    m = metrics if candidates is None else metrics[metrics["Model"].isin(candidates)]
    m = m.dropna(subset=[metric])
    return None if m.empty else str(m.loc[m[metric].idxmin(), "Model"])


def screen_sarimax(data: pd.DataFrame, target: str, configs: list[fc.SarimaxConfig], test_size: int,
                   period: int) -> pd.DataFrame:
    """Rolling-origin comparison of several SARIMAX orders on the same evaluation quarters."""
    rows = []
    n = len(data)
    for cfg in configs:
        preds, actual = [], []
        for i in range(n - test_size, n):
            try:
                preds.append(fc.sarimax_one_step(data[target].iloc[:i].rename(target), cfg))
            except fc.ForecastError:
                preds.append(np.nan)
            actual.append(float(data[target].iloc[i]))
        rows.append({"Configuration": cfg.label(), "Order": str(cfg.order), "Seasonal order": str(cfg.seasonal_order),
                     "Successful forecasts": int(np.isfinite(preds).sum()), **compute_metrics(actual, preds)})
    return pd.DataFrame(rows).sort_values("MAE").reset_index(drop=True)
