"""Session state, active dataset and cached model computations shared by all pages."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from config import settings
from src import data_loader, evaluation as ev, forecasting as fc
from src.preprocessing import DatasetBundle, filter_quarterly, filter_records, model_ready
from src.utils import get_logger, label_to_timestamp, quarter_labels

log = get_logger(__name__)

BEST = "Best by rolling-origin evaluation"
VAR_TRANSFORMS = {"Log differences": "log_diff", "First differences": "diff"}

# Widget values that must survive page changes. Streamlit discards a widget's state
# when its page is not rendered, so app.py re-assigns these keys on every run.
DEFAULTS = {
    "flt_start": None,
    "flt_end": None,
    "flt_countries": [],
    "cfg_target": settings.TARGET,
    "cfg_horizon": settings.DEFAULT_HORIZON,
    "cfg_ci": settings.DEFAULT_CI_LEVEL,
    "cfg_period": settings.DEFAULT_SEASONAL_PERIOD,
    "cfg_markers": True,
    "cfg_p": settings.DEFAULT_ORDER[0], "cfg_d": settings.DEFAULT_ORDER[1], "cfg_q": settings.DEFAULT_ORDER[2],
    "cfg_P": settings.DEFAULT_SEASONAL_ORDER[0], "cfg_D": settings.DEFAULT_SEASONAL_ORDER[1],
    "cfg_Q": settings.DEFAULT_SEASONAL_ORDER[2],
    "cfg_log": False,
    "cfg_var_vars": list(settings.TRAFFIC_COLUMNS),
    "cfg_var_transform": "Log differences",
    "cfg_var_maxlag": 4,
    "cfg_var_ic": "BIC",
    "cfg_var_dummies": False,
    "ev_models": [fc.NAIVE, fc.SARIMAX, fc.VAR_MODEL],
    "ev_test_size": settings.DEFAULT_TEST_SIZE,
    "ev_metric": "MAE",
    "lab_model": fc.SARIMAX,
    "ff_model": BEST,
    "ff_clip": False,
}


def init_state() -> None:
    for key, value in DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = list(value) if isinstance(value, list) else value
        else:
            st.session_state[key] = st.session_state[key]


# --------------------------------------------------------------------------- dataset
def _local_signature() -> tuple:
    return tuple((str(p), p.stat().st_mtime if p.exists() else None)
                 for p in (settings.COUNTRY_CSV, settings.QUARTERLY_CSV, settings.CARRIER_MONTHLY_CSV))


@st.cache_data(show_spinner="Loading and validating the dataset…")
def _cached_default(_signature: tuple) -> DatasetBundle:
    return data_loader.load_default()


@st.cache_data(show_spinner="Loading quarterly aggregate…")
def _cached_quarterly(_signature: tuple) -> DatasetBundle:
    return data_loader.load_quarterly_aggregate()


def get_bundle() -> DatasetBundle | None:
    if "bundle" not in st.session_state:
        try:
            st.session_state["bundle"] = _cached_default(_local_signature())
            st.session_state.pop("bundle_error", None)
        except data_loader.DataLoadError as exc:
            st.session_state["bundle_error"] = str(exc)
            return None
    return st.session_state["bundle"]


def set_bundle(bundle: DatasetBundle) -> None:
    """Activate a dataset. Filter widgets may already exist in this run, so their reset is
    deferred to ``sanitize_filters`` at the start of the next run (callers then ``st.rerun()``)."""
    st.session_state["bundle"] = bundle
    st.session_state["_reset_filters"] = True


def use_local(source: str) -> DatasetBundle:
    loader = _cached_quarterly if source == data_loader.SOURCE_QUARTERLY else _cached_default
    bundle = loader(_local_signature())
    set_bundle(bundle)
    return bundle


def reload_dataset() -> str:
    """Re-read local files (uploaded/remote datasets stay as they are)."""
    _cached_default.clear()
    _cached_quarterly.clear()
    current = st.session_state.get("bundle")
    if current is None or current.source in (data_loader.SOURCE_COUNTRY, data_loader.SOURCE_QUARTERLY):
        source = current.source if current else data_loader.SOURCE_COUNTRY
        try:
            use_local(source)
            return f"Reloaded {source.lower()}."
        except data_loader.DataLoadError as exc:
            return f"Reload failed, previous dataset kept: {exc}"
    return "The active dataset is an upload or remote copy; it was kept. Choose a local source to reload files."


def sanitize_filters(bundle: DatasetBundle) -> list[str]:
    labels = quarter_labels(bundle.quarterly.index)
    if st.session_state.pop("_reset_filters", False):
        st.session_state["flt_start"] = st.session_state["flt_end"] = None
        st.session_state["flt_countries"] = []
    start, end = st.session_state.get("flt_start"), st.session_state.get("flt_end")
    if not labels:
        st.session_state["flt_start"] = st.session_state["flt_end"] = None
    else:
        if start not in labels:
            st.session_state["flt_start"] = labels[0]
        if end not in labels:
            st.session_state["flt_end"] = labels[-1]
        if labels.index(st.session_state["flt_start"]) > labels.index(st.session_state["flt_end"]):
            st.session_state["flt_start"], st.session_state["flt_end"] = st.session_state["flt_end"], st.session_state["flt_start"]
    valid = set(bundle.countries)
    st.session_state["flt_countries"] = [c for c in st.session_state.get("flt_countries", []) if c in valid]
    if st.session_state["cfg_var_vars"] and st.session_state["cfg_target"] not in st.session_state["cfg_var_vars"]:
        st.session_state["cfg_var_vars"] = sorted({*st.session_state["cfg_var_vars"], st.session_state["cfg_target"]},
                                                  key=settings.TRAFFIC_COLUMNS.index)
    return labels


@dataclass
class Context:
    bundle: DatasetBundle
    quarterly: pd.DataFrame
    records: pd.DataFrame
    start: pd.Timestamp
    end: pd.Timestamp
    countries: list[str]
    target: str
    horizon: int
    ci: int
    period: int
    markers: bool

    @property
    def filter_note(self) -> str:
        who = f"{len(self.countries)} selected countries" if self.countries else "all countries"
        if not self.bundle.has_country:
            who = "aggregated totals"
        from src.utils import quarter_label
        return f"{quarter_label(self.start)} – {quarter_label(self.end)} · {who}"


def get_context() -> Context | None:
    bundle = get_bundle()
    if bundle is None:
        return None
    lo, hi = st.session_state.get("flt_start"), st.session_state.get("flt_end")
    start, end = (label_to_timestamp(lo), label_to_timestamp(hi)) if lo and hi else (None, None)
    countries = st.session_state.get("flt_countries", [])
    quarterly = filter_quarterly(bundle, countries, start, end)
    records = filter_records(bundle, countries, start, end)
    return Context(bundle=bundle, quarterly=quarterly, records=records,
                   start=quarterly.index.min() if len(quarterly) else start,
                   end=quarterly.index.max() if len(quarterly) else end,
                   countries=countries, target=st.session_state["cfg_target"],
                   horizon=int(st.session_state["cfg_horizon"]), ci=int(st.session_state["cfg_ci"]),
                   period=int(st.session_state["cfg_period"]), markers=bool(st.session_state["cfg_markers"]))


# --------------------------------------------------------------------------- model configuration
def sarimax_config(period: int | None = None) -> fc.SarimaxConfig:
    s = st.session_state
    return fc.SarimaxConfig(order=(int(s.cfg_p), int(s.cfg_d), int(s.cfg_q)),
                            seasonal_order=(int(s.cfg_P), int(s.cfg_D), int(s.cfg_Q), int(period or s.cfg_period)),
                            log=bool(s.cfg_log))


def var_config() -> fc.VarConfig:
    s = st.session_state
    return fc.VarConfig(variables=tuple(v for v in settings.TRAFFIC_COLUMNS if v in s.cfg_var_vars),
                        transform=VAR_TRANSFORMS[s.cfg_var_transform], max_lag=int(s.cfg_var_maxlag),
                        ic=s.cfg_var_ic.lower(), seasonal_dummies=bool(s.cfg_var_dummies))


# --------------------------------------------------------------------------- cached computations
@st.cache_data(show_spinner=False, max_entries=64)
def cached_forecast(model: str, quarterly: pd.DataFrame, target: str, horizon: int, ci: int, period: int,
                    sarimax_cfg: fc.SarimaxConfig, var_cfg: fc.VarConfig) -> fc.ForecastResult:
    return fc.run_forecast(model, quarterly, target, horizon, ci, period, sarimax_cfg, var_cfg)


@st.cache_data(show_spinner=False, max_entries=32)
def cached_rolling(quarterly: pd.DataFrame, target: str, models: tuple[str, ...], test_size: int, period: int,
                   sarimax_cfg: fc.SarimaxConfig, var_cfg: fc.VarConfig) -> dict:
    return ev.rolling_origin(quarterly, target, list(models), test_size, period, sarimax_cfg, var_cfg)


@st.cache_data(show_spinner=False, max_entries=8)
def cached_screening(quarterly: pd.DataFrame, target: str, configs: tuple, test_size: int, period: int):
    return ev.screen_sarimax(quarterly, target, list(configs), test_size, period)


def evaluation_inputs(ctx: Context) -> tuple[list[str], int]:
    models = [m for m in st.session_state["ev_models"] if m in fc.MODEL_NAMES] or [fc.NAIVE]
    return models, int(st.session_state["ev_test_size"])


def get_evaluation(ctx: Context) -> tuple[dict | None, str | None]:
    """Rolling-origin evaluation for the current settings: (result, error message)."""
    problems = model_ready(ctx.quarterly, list(settings.TRAFFIC_COLUMNS))
    if problems:
        return None, " ".join(problems)
    models, test_size = evaluation_inputs(ctx)
    if fc.VAR_MODEL in models and ctx.target not in var_config().variables:
        models = [m for m in models if m != fc.VAR_MODEL]
    try:
        with st.spinner(f"Rolling-origin evaluation: {test_size} origins × {len(models)} model(s)…"):
            return cached_rolling(ctx.quarterly, ctx.target, tuple(models), test_size, ctx.period,
                                  sarimax_config(ctx.period), var_config()), None
    except (ValueError, fc.ForecastError) as exc:
        return None, str(exc)


def get_forecast(ctx: Context, model: str, target: str | None = None, horizon: int | None = None):
    target = target or ctx.target
    cols = list(var_config().variables) if model == fc.VAR_MODEL else (
        [target] + fc.exog_columns_for(target) if model == fc.EXOG_OPERATIONAL else [target])
    problems = model_ready(ctx.quarterly, cols)
    if problems:
        return None, " ".join(problems)
    try:
        with st.spinner(f"Fitting {model}…"):
            return cached_forecast(model, ctx.quarterly, target, int(horizon or ctx.horizon), ctx.ci, ctx.period,
                                   sarimax_config(ctx.period), var_config()), None
    except fc.ForecastError as exc:
        return None, str(exc)


def resolve_future_model(ctx: Context, evaluation: dict | None) -> tuple[str, str]:
    choice = st.session_state["ff_model"]
    if choice != BEST:
        return choice, "Selected manually."
    metric = st.session_state["ev_metric"]
    best = ev.best_model(evaluation["metrics"], metric, fc.FUTURE_CAPABLE) if evaluation else None
    if best is None:
        return fc.SARIMAX, "No evaluation result available; SARIMAX used as the default."
    return best, (f"Lowest {metric} in rolling-origin evaluation ({evaluation['period_label']}) among models "
                  "that can forecast without future observed values.")
