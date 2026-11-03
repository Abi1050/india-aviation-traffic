import plotly.graph_objects as go
import streamlit as st

from config.settings import LABELS, QUARTER_COLORS, TRAFFIC_COLUMNS
from src import diagnostics as dg, forecasting as fc, state, ui, visualization as viz
from src.shell import ROOT

ctx = state.get_context()
ui.no_data_stop(ctx)
ui.page_header("Time-Series Diagnostics",
               "Stationarity, autocorrelation and seasonal structure of the quarterly series.",
               eyebrow="Data & analysis")
q = ctx.quarterly
n = int(q.dropna(how="all").shape[0])
st.info(f"The selection contains {n} quarterly observations. With a sample this short, unit-root and "
        "autocorrelation tests have limited power, so conclusions are indicative rather than definitive.")

# --------------------------------------------------------------------------- ADF
ui.section("Stationarity testing – Augmented Dickey-Fuller",
           "H0: the series has a unit root (non-stationary). A p-value below the significance level is evidence "
           "against H0. Failing to reject is not proof of a unit root.")
c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
variables = c1.multiselect("Traffic variables", TRAFFIC_COLUMNS, default=TRAFFIC_COLUMNS,
                           format_func=lambda c: LABELS[c], key="ts_adf_vars")
transforms = c2.multiselect("Transformations", dg.TRANSFORMS, default=["Level", "First difference"], key="ts_adf_tr")
alpha = c3.selectbox("Significance level", [0.01, 0.05, 0.10], index=1, key="ts_adf_alpha")
regression = c4.selectbox("Deterministic terms", ["c", "ct"], key="ts_adf_reg",
                          format_func=lambda r: "Constant" if r == "c" else "Constant + trend")
if variables and transforms:
    adf = dg.adf_table(q, variables, transforms, alpha, ctx.period, regression)
    ui.table(adf, number_format={"ADF statistic": "%.3f", "p-value": "%.4f", "Critical 1%": "%.3f",
                                 "Critical 5%": "%.3f", "Critical 10%": "%.3f"})
    st.session_state["adf_last"] = adf
    lines = []
    for v in variables:
        sub = adf[adf["Variable"] == v].set_index("Transform")
        if "Level" in sub.index and sub.loc["Level", "Stationary"] is not None:
            lvl = sub.loc["Level"]
            text = (f"{LABELS[v]} (level): p = {lvl['p-value']:.3f} – "
                    + ("unit root rejected at this level." if lvl["Stationary"] else "unit root not rejected."))
            if "First difference" in sub.index and sub.loc["First difference", "Stationary"] is not None:
                fd = sub.loc["First difference"]
                text += (f" First difference: p = {fd['p-value']:.3f}"
                         + (" – stationary, supporting d = 1." if fd["Stationary"] and not lvl["Stationary"]
                            else " – stationary." if fd["Stationary"] else " – still not clearly stationary."))
            lines.append(text)
    ui.insights(lines)
    st.caption(f"Lag length chosen by AIC. Interpretation at the {alpha:.0%} significance level. Differencing is only "
               "suggested where the level test does not reject the unit root.")

# --------------------------------------------------------------------------- ACF / PACF
ui.section("Autocorrelation (ACF) and partial autocorrelation (PACF)")
c1, c2, c3 = st.columns([2, 2, 1])
var = c1.selectbox("Traffic variable", TRAFFIC_COLUMNS, format_func=lambda c: LABELS[c], key="ts_acf_var")
tr = c2.selectbox("Transformation", dg.TRANSFORMS, index=1, key="ts_acf_tr")
try:
    series = dg.transform_series(q[var].dropna(), tr, ctx.period)
    max_lag = max(2, len(series) // 2 - 1)
    nlags = c3.number_input("Lags", 1, max_lag, min(dg.default_nlags(len(series)), max_lag), key="ts_acf_n")
    values = dg.acf_pacf(series, int(nlags))
    c1, c2 = st.columns(2)
    with c1:
        ui.chart(viz.correlogram(values, "ACF", f"Autocorrelation Function – {LABELS[var]} ({tr.lower()})"))
    with c2:
        ui.chart(viz.correlogram(values, "PACF", f"Partial Autocorrelation Function – {LABELS[var]} ({tr.lower()})"))
    sig = values[(values["Lag"] > 0) & (values["ACF"].abs() > values["Bound"])]["Lag"].tolist()
    st.caption(f"{len(series)} observations; lag limit about a quarter of the sample (max 12). "
               + (f"ACF exceeds the approximate 95% bound at lag(s) {', '.join(map(str, sig))}."
                  if sig else "No ACF value exceeds the approximate 95% bound."))
except ValueError as exc:
    st.warning(f"ACF/PACF not computed: {exc}")

# --------------------------------------------------------------------------- seasonality
ui.section("Quarterly seasonality", "Each line follows one quarter of the year across years (seasonal sub-series).")
var = st.selectbox("Traffic variable", TRAFFIC_COLUMNS, format_func=lambda c: LABELS[c], key="ts_seas_var")
s = q[var].dropna()
fig = go.Figure()
for k in range(1, 5):
    sub = s[s.index.quarter == k]
    fig.add_trace(go.Scatter(x=sub.index.year, y=sub.values, name=f"Q{k}", mode="lines+markers",
                             line=dict(color=QUARTER_COLORS[k - 1], width=2),
                             hovertemplate="%{x} Q" + str(k) + ": %{y:,.0f}<extra></extra>"))
viz.apply_theme(fig, f"Seasonal Sub-series – {LABELS[var]}", "Year",
                "Passengers" if var.startswith("Pax") else "Freight (source units)", viz.HEIGHT_SECONDARY)
fig.update_layout(hovermode="x unified")
fig.update_yaxes(tickformat="~s")
ui.chart(fig)

# --------------------------------------------------------------------------- model diagnostics overview
ui.section("Fitted-model diagnostics overview",
           "In-sample residuals come from a model fitted to all selected quarters. Rolling forecast errors "
           "(actual − predicted) come from the Model Evaluation page; they are different quantities.")
result, err = state.get_forecast(ctx, fc.SARIMAX)
if result is None:
    st.warning(f"SARIMAX could not be fitted: {err}")
else:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**In-sample residuals – {result.spec}**")
        try:
            p, d, qq = state.sarimax_config().order
            P, D, Q, _ = state.sarimax_config().seasonal_order
            lb = dg.ljung_box(result.residuals, [4, 8], model_df=p + qq + P + Q)
            ui.table(lb, number_format={"Q statistic": "%.3f", "p-value": "%.4f"})
            st.caption("Ljung-Box H0: no residual autocorrelation up to the lag. Degrees of freedom are adjusted for "
                       "the ARMA terms.")
        except ValueError as exc:
            st.warning(str(exc))
    with c2:
        st.markdown("**Rolling-origin forecast errors**")
        evaluation, eerr = state.get_evaluation(ctx)
        if evaluation and fc.SARIMAX in evaluation["models"]:
            e = evaluation["forecasts"]["Actual"] - evaluation["forecasts"][fc.SARIMAX]
            try:
                ui.table(dg.ljung_box(e, [4]), number_format={"Q statistic": "%.3f", "p-value": "%.4f"})
            except ValueError as exc:
                st.warning(str(exc))
            note = dg.small_sample_note(int(e.notna().sum()))
            if note:
                st.caption(note)
        else:
            st.info(eerr or "Include SARIMAX on the Model Evaluation page to see its forecast errors.")
    st.page_link(ROOT / "app_pages" / "8_Residual_Analysis.py", label="Open full residual analysis",
                 icon=":material/arrow_forward:")
