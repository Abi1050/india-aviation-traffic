"""Forecasting models: Seasonal Naive, SARIMAX (optionally with exogenous variables) and VAR.

Every function validates its inputs and raises ``ForecastError`` with a readable
message instead of failing deep inside statsmodels.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.tsa.api import VAR
from statsmodels.tsa.statespace.sarimax import SARIMAX as SARIMAXModel
from statsmodels.tsa.stattools import adfuller

from config.settings import TRAFFIC_COLUMNS
from src.utils import quarter_label

NAIVE = "Seasonal Naive"
SARIMAX = "SARIMAX"
VAR_MODEL = "VAR"
EXOG_CONDITIONAL = "SARIMAX + exog (conditional)"
EXOG_OPERATIONAL = "SARIMAX + exog (operational)"
MODEL_NAMES = [NAIVE, SARIMAX, VAR_MODEL, EXOG_CONDITIONAL, EXOG_OPERATIONAL]
FUTURE_CAPABLE = [NAIVE, SARIMAX, VAR_MODEL, EXOG_OPERATIONAL]

MAX_HORIZON = 24
OBS_PER_COEF = 5


class ForecastError(ValueError):
    """A model could not be fitted or produced invalid output."""


@dataclass(frozen=True)
class SarimaxConfig:
    order: tuple[int, int, int] = (1, 1, 1)
    seasonal_order: tuple[int, int, int, int] = (1, 1, 0, 4)
    log: bool = False

    def label(self) -> str:
        p, d, q = self.order
        P, D, Q, s = self.seasonal_order
        return f"SARIMAX({p},{d},{q})({P},{D},{Q},{s})" + (" on log values" if self.log else "")


@dataclass(frozen=True)
class VarConfig:
    variables: tuple[str, ...] = tuple(TRAFFIC_COLUMNS)
    transform: str = "log_diff"          # "log_diff" or "diff"
    max_lag: int = 4                     # upper bound; the data-driven cap may be lower
    ic: str = "bic"
    seasonal_dummies: bool = False

    def label(self) -> str:
        tr = "log differences" if self.transform == "log_diff" else "first differences"
        return f"VAR on {tr} of {len(self.variables)} variables" + (" + quarter dummies" if self.seasonal_dummies else "")


@dataclass
class ForecastResult:
    model: str
    target: str
    spec: str
    ci_level: int
    forecast: pd.DataFrame                 # index Date; columns Forecast, Lower, Upper
    fitted: pd.Series                      # in-sample fitted values on the original scale
    residuals: pd.Series                   # in-sample residuals on the model scale
    residual_scale: str
    n_obs: int
    aic: float = float("nan")
    bic: float = float("nan")
    converged: bool | None = None
    warnings: list[str] = field(default_factory=list)   # issues the user should act on or weigh
    notes: list[str] = field(default_factory=list)      # informational remarks about the method
    summary: str = ""
    params: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- helpers
def check_horizon(horizon) -> int:
    if isinstance(horizon, bool) or not float(horizon).is_integer() or int(horizon) < 1:
        raise ForecastError("Forecast horizon must be a positive whole number of quarters.")
    if int(horizon) > MAX_HORIZON:
        raise ForecastError(f"Forecast horizon is limited to {MAX_HORIZON} quarters for this short series.")
    return int(horizon)


def future_index(last: pd.Timestamp, horizon: int) -> pd.DatetimeIndex:
    start = pd.Timestamp(last) + pd.offsets.QuarterBegin(startingMonth=1)
    return pd.date_range(start, periods=horizon, freq="QS-JAN", name="Date")


def check_series(series: pd.Series, name: str | None = None, positive: bool = False) -> pd.Series:
    name = name or str(series.name)
    if series is None or len(series) == 0:
        raise ForecastError(f"{name}: no observations.")
    try:
        s = series.astype(float)
    except (TypeError, ValueError) as exc:
        raise ForecastError(f"{name}: values are not numeric.") from exc
    if s.isna().any():
        raise ForecastError(f"{name}: {int(s.isna().sum())} missing quarter(s); models need a complete series.")
    if not np.isfinite(s.to_numpy()).all():
        raise ForecastError(f"{name}: contains non-finite values.")
    if positive and (s <= 0).any():
        raise ForecastError(f"{name}: log transformation needs strictly positive values.")
    return s


def z_value(ci_level: int) -> float:
    if not 50 <= ci_level < 100:
        raise ForecastError("Confidence level must be between 50 and 99.")
    return float(stats.norm.ppf(0.5 + ci_level / 200))


def _finite_forecast(df: pd.DataFrame, model: str) -> None:
    if not np.isfinite(df[["Forecast", "Lower", "Upper"]].to_numpy(dtype=float)).all():
        raise ForecastError(f"{model} produced non-finite forecasts; try a simpler configuration.")


def interval_warnings(fc: pd.DataFrame) -> list[str]:
    out = []
    if (fc["Lower"] < 0).any():
        out.append("Some lower interval bounds are below zero, which is impossible for traffic counts. "
                   "They are shown unchanged; a log-scale model keeps bounds positive.")
    ratio = (fc["Upper"] - fc["Lower"]) / fc["Forecast"].abs().replace(0, np.nan)
    if ratio.max() > 1.5:
        out.append(f"Intervals become very wide (up to {ratio.max():.0%} of the point forecast) – "
                   "long-horizon uncertainty is large for this short series.")
    return out


# --------------------------------------------------------------------------- seasonal naive
def seasonal_naive_forecast(series: pd.Series, horizon: int, period: int = 4, ci_level: int = 95) -> ForecastResult:
    horizon = check_horizon(horizon)
    s = check_series(series)
    if len(s) < period + 2:
        raise ForecastError(f"Seasonal Naive needs at least {period + 2} observations; found {len(s)}.")
    idx = future_index(s.index[-1], horizon)
    values = np.array([s.iloc[len(s) - period + ((h - 1) % period)] for h in range(1, horizon + 1)])
    fitted = s.shift(period)
    resid = (s - fitted).dropna()
    sigma = float(np.sqrt(np.mean(resid ** 2)))
    k = np.array([(h - 1) // period + 1 for h in range(1, horizon + 1)])
    half = z_value(ci_level) * sigma * np.sqrt(k)
    fc = pd.DataFrame({"Forecast": values, "Lower": values - half, "Upper": values + half}, index=idx)
    _finite_forecast(fc, NAIVE)
    return ForecastResult(
        model=NAIVE, target=str(s.name), spec=f"Seasonal Naive (period {period})", ci_level=ci_level,
        forecast=fc, fitted=fitted, residuals=resid, residual_scale="original units", n_obs=len(s),
        warnings=interval_warnings(fc),
        notes=["Intervals use a normal approximation: residual RMSE × √(seasons ahead)."],
        params={"period": period, "residual RMSE": sigma,
                "interval": "Normal approximation, sd × √(number of seasons ahead)"},
    )


def seasonal_naive_one_step(train: pd.Series, period: int = 4) -> float:
    if len(train) < period:
        raise ForecastError(f"Seasonal Naive needs {period} observations of history.")
    return float(train.iloc[-period])


# --------------------------------------------------------------------------- SARIMAX
def sarimax_min_obs(cfg: SarimaxConfig, n_exog: int = 0) -> int:
    p, d, q = cfg.order
    P, D, Q, s = cfg.seasonal_order
    n_params = p + q + P + Q + 1 + n_exog
    return d + D * s + max(p + P * s, q + Q * s, 1) + max(3 * n_params, 2 * s)


def _fit_sarimax(y: pd.Series, cfg: SarimaxConfig, exog: pd.DataFrame | None = None):
    n_exog = 0 if exog is None else exog.shape[1]
    need = sarimax_min_obs(cfg, n_exog)
    if len(y) < need:
        raise ForecastError(f"{cfg.label()} needs at least {need} observations; found {len(y)}.")
    if any(v < 0 for v in cfg.order + cfg.seasonal_order):
        raise ForecastError("SARIMAX orders must be non-negative.")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            model = SARIMAXModel(y, exog=exog, order=cfg.order, seasonal_order=cfg.seasonal_order,
                                 enforce_stationarity=False, enforce_invertibility=False)
            res = model.fit(disp=False, maxiter=200)
        except (ValueError, np.linalg.LinAlgError, IndexError) as exc:
            raise ForecastError(f"{cfg.label()} could not be fitted: {exc}") from exc
    messages = sorted({str(w.message).split("\n")[0] for w in caught
                       if "frequency" not in str(w.message) and "date index" not in str(w.message)})
    return res, messages


def _prep_sarimax_inputs(series, cfg, exog):
    y = check_series(series, positive=cfg.log)
    if exog is not None:
        exog = pd.DataFrame({c: check_series(exog[c], c, positive=cfg.log) for c in exog.columns}, index=y.index)
    if cfg.log:
        y = np.log(y)
        exog = np.log(exog) if exog is not None else None
    return y, exog


def sarimax_forecast(series: pd.Series, horizon: int, cfg: SarimaxConfig, ci_level: int = 95,
                     exog: pd.DataFrame | None = None, exog_future: pd.DataFrame | None = None) -> ForecastResult:
    horizon = check_horizon(horizon)
    y, ex = _prep_sarimax_inputs(series, cfg, exog)
    if ex is not None:
        if exog_future is None or len(exog_future) != horizon:
            raise ForecastError("Future exogenous values are required for every forecast quarter.")
        exf = np.log(exog_future.astype(float)) if cfg.log else exog_future.astype(float)
    else:
        exf = None
    res, msgs = _fit_sarimax(y, cfg, ex)
    alpha = 1 - ci_level / 100
    pred = res.get_forecast(steps=horizon, exog=None if exf is None else exf.to_numpy())
    mean = np.asarray(pred.predicted_mean, dtype=float)
    ci = np.asarray(pred.conf_int(alpha=alpha), dtype=float)
    idx = future_index(series.index[-1], horizon)
    fc = pd.DataFrame({"Forecast": mean, "Lower": ci[:, 0], "Upper": ci[:, 1]}, index=idx)
    if cfg.log:
        fc = np.exp(fc)
    _finite_forecast(fc, cfg.label())
    d, D, s = cfg.order[1], cfg.seasonal_order[1], cfg.seasonal_order[3]
    burn = d + D * s
    fitted = pd.Series(np.asarray(res.fittedvalues, dtype=float), index=series.index, name="Fitted")
    fitted = np.exp(fitted) if cfg.log else fitted
    fitted.iloc[:burn] = np.nan
    resid = pd.Series(np.asarray(res.resid, dtype=float), index=series.index, name="Residual").iloc[burn:]
    converged = bool(res.mle_retvals.get("converged", True)) if hasattr(res, "mle_retvals") and res.mle_retvals else None
    notes = list(msgs)
    if converged is False:
        notes.insert(0, "The optimiser did not report convergence; treat estimates with caution.")
    info = []
    if burn:
        info.append(f"The first {burn} in-sample residuals are excluded: they are start-up effects of "
                     f"differencing (d={d}, D={D}, s={s}), not genuine errors.")
    notes.extend(interval_warnings(fc))
    return ForecastResult(
        model=EXOG_OPERATIONAL if exog is not None else SARIMAX, target=str(series.name),
        spec=cfg.label() + (f" with exogenous {', '.join(exog.columns)}" if exog is not None else ""),
        ci_level=ci_level, forecast=fc, fitted=fitted, residuals=resid,
        residual_scale="log units" if cfg.log else "original units", n_obs=len(y),
        aic=float(res.aic), bic=float(res.bic), converged=converged, warnings=notes, notes=info,
        summary=str(res.summary()),
        params={k: float(v) for k, v in res.params.items()} if hasattr(res.params, "items") else {},
    )


def sarimax_one_step(train: pd.Series, cfg: SarimaxConfig, exog_train: pd.DataFrame | None = None,
                     exog_next: pd.DataFrame | None = None) -> float:
    y, ex = _prep_sarimax_inputs(train, cfg, exog_train)
    res, _ = _fit_sarimax(y, cfg, ex)
    exn = None
    if ex is not None:
        exn = np.log(exog_next.astype(float)) if cfg.log else exog_next.astype(float)
        exn = exn.to_numpy()
    value = float(np.asarray(res.forecast(steps=1, exog=exn))[0])
    value = float(np.exp(value)) if cfg.log else value
    if not np.isfinite(value):
        raise ForecastError("Non-finite one-step forecast.")
    return value


def project_exog(exog: pd.DataFrame, horizon: int, period: int = 4) -> pd.DataFrame:
    """Operational exogenous inputs: each regressor projected by Seasonal Naive using only
    data available at the forecast origin."""
    idx = future_index(exog.index[-1], horizon)
    return pd.DataFrame(
        {c: [exog[c].iloc[len(exog) - period + ((h - 1) % period)] for h in range(1, horizon + 1)]
         for c in exog.columns}, index=idx)


# --------------------------------------------------------------------------- VAR
def _var_transform(df: pd.DataFrame, transform: str) -> pd.DataFrame:
    if transform == "log_diff":
        if (df <= 0).any().any():
            raise ForecastError("Log differences need strictly positive values; choose first differences instead.")
        return np.log(df).diff().dropna()
    if transform == "diff":
        return df.diff().dropna()
    raise ForecastError(f"Unknown VAR transform {transform}.")


def _quarter_dummies(index: pd.DatetimeIndex) -> np.ndarray:
    q = np.asarray(index.quarter)
    return np.column_stack([(q == k).astype(float) for k in (2, 3, 4)])


def var_lag_cap(n_transformed: int, k: int, max_lag: int, seasonal_dummies: bool) -> int:
    """Largest lag order with at least five observations per estimated coefficient in each equation.

    This guards against over-parameterised VARs on the short quarterly sample.
    """
    extra = 3 if seasonal_dummies else 0
    best = 0
    for p in range(1, max_lag + 1):
        if n_transformed - p >= OBS_PER_COEF * (k * p + 1 + extra):
            best = p
    return best


def var_suitability(df: pd.DataFrame, cfg: VarConfig, alpha: float = 0.05) -> dict:
    problems, notes, adf_rows = [], [], []
    variables = list(cfg.variables)
    if len(variables) < 2:
        problems.append("VAR needs at least two variables.")
    missing = [v for v in variables if v not in df.columns]
    if missing:
        problems.append(f"Unknown variables: {', '.join(missing)}.")
    if problems:
        return {"ok": False, "problems": problems, "notes": notes, "lag_cap": 0, "adf": pd.DataFrame()}
    data = df[variables]
    if data.isna().any().any():
        problems.append("Selected variables contain missing quarters.")
    elif not np.isfinite(data.to_numpy(dtype=float)).all():
        problems.append("Selected variables contain non-finite values.")
    if problems:
        return {"ok": False, "problems": problems, "notes": notes, "lag_cap": 0, "adf": pd.DataFrame()}
    try:
        z = _var_transform(data.astype(float), cfg.transform)
    except ForecastError as exc:
        return {"ok": False, "problems": [str(exc)], "notes": notes, "lag_cap": 0, "adf": pd.DataFrame()}
    cap = var_lag_cap(len(z), len(variables), cfg.max_lag, cfg.seasonal_dummies)
    if cap < 1:
        problems.append(f"{len(z)} transformed observations are too few for a {len(variables)}-variable VAR "
                        "(need at least five observations per coefficient). Use fewer variables or SARIMAX.")
    for v in variables:
        try:
            p = adfuller(z[v], autolag="AIC")[1]
            adf_rows.append({"Variable": v, "ADF p-value (transformed)": p, "Stationary at 5%": p < alpha})
            if p >= alpha:
                notes.append(f"{v}: transformed series is not clearly stationary (ADF p = {p:.3f}).")
        except ValueError:
            pass
    return {"ok": not problems, "problems": problems, "notes": notes, "lag_cap": cap,
            "adf": pd.DataFrame(adf_rows), "n_transformed": len(z)}


def _fit_var(df: pd.DataFrame, cfg: VarConfig):
    variables = list(cfg.variables)
    data = pd.DataFrame({v: check_series(df[v], v, positive=cfg.transform == "log_diff") for v in variables})
    z = _var_transform(data, cfg.transform)
    cap = var_lag_cap(len(z), len(variables), cfg.max_lag, cfg.seasonal_dummies)
    if cap < 1:
        raise ForecastError(f"Too few observations ({len(z)}) for a {len(variables)}-variable VAR.")
    exog = _quarter_dummies(z.index) if cfg.seasonal_dummies else None
    model = VAR(z.to_numpy(), exog=exog)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            selected = model.select_order(maxlags=cap, trend="c").selected_orders.get(cfg.ic, 1)
        except (ValueError, np.linalg.LinAlgError):
            selected = 1
        lag = int(min(max(selected or 1, 1), cap))
        try:
            res = model.fit(lag, trend="c")
        except (ValueError, np.linalg.LinAlgError) as exc:
            raise ForecastError(f"VAR could not be fitted: {exc}") from exc
    return res, lag, data, z, cap


def var_forecast(df: pd.DataFrame, target: str, horizon: int, cfg: VarConfig, ci_level: int = 95) -> ForecastResult:
    horizon = check_horizon(horizon)
    if target not in cfg.variables:
        raise ForecastError(f"The target {target} must be one of the VAR variables.")
    res, lag, data, z, cap = _fit_var(df, cfg)
    i = list(cfg.variables).index(target)
    idx = future_index(data.index[-1], horizon)
    exf = _quarter_dummies(idx) if cfg.seasonal_dummies else None
    mean_z = res.forecast(z.to_numpy()[-lag:], steps=horizon, exog_future=exf)
    # Analytic interval for the cumulated (level) forecast: the h-step level error is
    # sum_{j<h} C_j u, with C_j the cumulative sum of MA coefficient matrices.
    psi = res.ma_rep(maxn=horizon - 1)
    cum = np.cumsum(psi, axis=0)
    sigma_u = np.asarray(res.sigma_u)
    var_level = np.cumsum([(c @ sigma_u @ c.T)[i, i] for c in cum])
    log_scale = cfg.transform == "log_diff"
    base = np.log(data[target].iloc[-1]) if log_scale else data[target].iloc[-1]
    centre = base + np.cumsum(mean_z[:, i])
    half = z_value(ci_level) * np.sqrt(var_level)
    fc = pd.DataFrame({"Forecast": centre, "Lower": centre - half, "Upper": centre + half}, index=idx)
    if log_scale:
        fc = np.exp(fc)
    _finite_forecast(fc, "VAR")
    # In-sample one-step fitted values mapped back to levels.
    fitted_z = pd.Series(np.asarray(res.fittedvalues)[:, i], index=z.index[lag:])
    prev = (np.log(data[target]) if log_scale else data[target]).shift(1).reindex(fitted_z.index)
    fitted = (np.exp(prev + fitted_z) if log_scale else prev + fitted_z).reindex(data.index)
    resid = pd.Series(np.asarray(res.resid)[:, i], index=z.index[lag:], name="Residual")
    notes = []
    if not res.is_stable():
        notes.append("The estimated VAR is not stable (roots on or outside the unit circle); forecasts may be unreliable.")
    notes.extend(interval_warnings(fc))
    info = [f"Lag order {lag} chosen by {cfg.ic.upper()} (maximum allowed by sample size: {cap}).",
            "Intervals reflect shock uncertainty only, not parameter-estimation uncertainty."]
    return ForecastResult(
        model=VAR_MODEL, target=target, spec=cfg.label() + f", lag {lag}", ci_level=ci_level, forecast=fc,
        fitted=fitted, residuals=resid, residual_scale="log-difference units" if log_scale else "differenced units",
        n_obs=len(z), aic=float(res.aic), bic=float(res.bic), converged=None, warnings=notes, notes=info,
        summary=str(res.summary()), params={"lag order": lag, "variables": ", ".join(cfg.variables)},
    )


def var_one_step(train: pd.DataFrame, target: str, cfg: VarConfig) -> float:
    res, lag, data, z, _ = _fit_var(train, cfg)
    i = list(cfg.variables).index(target)
    nxt = future_index(data.index[-1], 1)
    exf = _quarter_dummies(nxt) if cfg.seasonal_dummies else None
    step = float(res.forecast(z.to_numpy()[-lag:], steps=1, exog_future=exf)[0, i])
    last = float(data[target].iloc[-1])
    value = last * float(np.exp(step)) if cfg.transform == "log_diff" else last + step
    if not np.isfinite(value):
        raise ForecastError("Non-finite VAR forecast.")
    return value


# --------------------------------------------------------------------------- dispatcher
def exog_columns_for(target: str) -> list[str]:
    """Explanatory variables used by the notebook: the other three traffic series."""
    return [c for c in TRAFFIC_COLUMNS if c != target]


def run_forecast(model: str, quarterly: pd.DataFrame, target: str, horizon: int, ci_level: int,
                 period: int, sarimax_cfg: SarimaxConfig, var_cfg: VarConfig) -> ForecastResult:
    series = quarterly[target].rename(target)
    if model == NAIVE:
        return seasonal_naive_forecast(series, horizon, period, ci_level)
    if model == SARIMAX:
        return sarimax_forecast(series, horizon, sarimax_cfg, ci_level)
    if model == EXOG_OPERATIONAL:
        exog = quarterly[exog_columns_for(target)]
        result = sarimax_forecast(series, horizon, sarimax_cfg, ci_level, exog=exog,
                                  exog_future=project_exog(exog, horizon, period))
        result.notes.append("Future exogenous values are Seasonal Naive projections; their uncertainty "
                               "is not included in the interval.")
        return result
    if model == VAR_MODEL:
        return var_forecast(quarterly, target, horizon, var_cfg, ci_level)
    if model == EXOG_CONDITIONAL:
        raise ForecastError("Conditional exogenous evaluation uses observed future regressors and cannot "
                            "produce a genuine future forecast. Choose the operational variant.")
    raise ForecastError(f"Unknown model {model}.")


def validate_forecast(fc: pd.DataFrame, history_index: pd.DatetimeIndex, horizon: int) -> pd.DataFrame:
    """Checks shown on the Future Forecast page and written into reports."""
    idx = fc.index
    expected = future_index(history_index.max(), horizon)
    checks = [
        ("Forecast horizon matches selection", len(fc) == horizon, f"{len(fc)} of {horizon} quarters"),
        ("Forecast dates are consecutive quarters", idx.equals(expected),
         f"{quarter_label(idx[0])} to {quarter_label(idx[-1])}" if len(idx) else "–"),
        ("No overlap with observed quarters", idx.min() > history_index.max() if len(idx) else False,
         f"Last observed: {quarter_label(history_index.max())}"),
        ("All values finite", bool(np.isfinite(fc[["Forecast", "Lower", "Upper"]].to_numpy(dtype=float)).all()), ""),
        ("Bounds ordered (lower ≤ forecast ≤ upper)",
         bool(((fc["Lower"] <= fc["Forecast"]) & (fc["Forecast"] <= fc["Upper"])).all()), ""),
        ("Point forecasts non-negative", bool((fc["Forecast"] >= 0).all()), ""),
        ("Lower bounds non-negative", bool((fc["Lower"] >= 0).all()),
         "" if (fc["Lower"] >= 0).all() else "Negative lower bounds are kept as estimated and flagged."),
    ]
    return pd.DataFrame(checks, columns=["Check", "Passed", "Details"])
