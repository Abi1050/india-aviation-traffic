import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.settings import COLORS, LABELS, MODEL_COLORS, TRAFFIC_COLUMNS
from src import forecasting as fc, state, ui, visualization as viz
from src.utils import fmt_number, quarter_label

ctx = state.get_context()
ui.no_data_stop(ctx)
ui.page_header("Forecasting Laboratory",
               "Configure, fit and inspect Seasonal Naive, SARIMAX and VAR forecasts.", eyebrow="Modelling")

target = ctx.target
y_title = "Passengers" if target.startswith("Pax") else "Freight (source units)"
st.caption(f"Target **{LABELS[target]}** · horizon **{ctx.horizon} quarters** · **{ctx.ci}%** intervals · "
           f"seasonal period **{ctx.period}** (change these in the sidebar) · data: {ctx.filter_note}")

ui.section("Model selection")
lab_models = [fc.NAIVE, fc.SARIMAX, fc.EXOG_OPERATIONAL, fc.VAR_MODEL]
st.segmented_control("Forecasting model", lab_models, key="lab_model", required=True)
model = st.session_state["lab_model"] or fc.SARIMAX

if model in (fc.SARIMAX, fc.EXOG_OPERATIONAL):
    with st.form("sarimax_form"):
        st.markdown("**SARIMAX parameters** – defaults follow the notebook: order (1, 1, 1), seasonal (1, 1, 0, s). "
                    "They are starting values, not proven optima.")
        cols = st.columns(7)
        for col, (key, label) in zip(cols, [("cfg_p", "p (AR)"), ("cfg_d", "d (diff.)"), ("cfg_q", "q (MA)"),
                                            ("cfg_P", "P (seasonal AR)"), ("cfg_D", "D (seasonal diff.)"),
                                            ("cfg_Q", "Q (seasonal MA)")]):
            col.number_input(label, 0, 2 if key in ("cfg_d", "cfg_D") else 3, step=1, key=key)
        cols[6].checkbox("Model log values", key="cfg_log",
                         help="Fits SARIMAX to log(traffic). Forecasts and bounds are transformed back with exp(); "
                              "the point forecast is then a median and bounds stay positive.")
        st.form_submit_button("Run forecast", type="primary", icon=":material/play_arrow:")
    if model == fc.EXOG_OPERATIONAL:
        st.info(f"Exogenous regressors: {', '.join(LABELS[c] for c in fc.exog_columns_for(target))}. Their future "
                "values are unknown, so each is projected with Seasonal Naive from data available at the forecast "
                "origin (operational setting).")
elif model == fc.VAR_MODEL:
    with st.form("var_form"):
        st.markdown("**VAR settings** – the model is fitted on transformed (differenced) series and forecasts are "
                    "cumulated back to levels.")
        c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
        c1.multiselect("Variables (must include the target)", TRAFFIC_COLUMNS, key="cfg_var_vars",
                       format_func=lambda c: LABELS[c])
        c2.selectbox("Transformation", list(state.VAR_TRANSFORMS), key="cfg_var_transform")
        c3.number_input("Max lag", 1, 8, step=1, key="cfg_var_maxlag")
        c4.selectbox("Lag criterion", ["BIC", "AIC"], key="cfg_var_ic")
        st.checkbox("Add quarter dummies (3 extra coefficients per equation)", key="cfg_var_dummies")
        st.form_submit_button("Run forecast", type="primary", icon=":material/play_arrow:")
    vcfg = state.var_config()
    if target not in vcfg.variables:
        st.error(f"The VAR variables must include the target {LABELS[target]}.")
        st.stop()
    suit = fc.var_suitability(ctx.quarterly, vcfg)
    with st.expander("VAR suitability checks", expanded=not suit["ok"]):
        st.markdown(f"- Variables: {len(vcfg.variables)} · transformed observations: {suit.get('n_transformed', '–')}"
                    f" · largest lag allowed by the sample-size rule (≥ {fc.OBS_PER_COEF} observations per "
                    f"coefficient): **{suit['lag_cap']}**")
        for p in suit["problems"]:
            st.error(p)
        for note in suit["notes"]:
            st.warning(note)
        if not suit["adf"].empty:
            ui.table(suit["adf"], number_format={"ADF p-value (transformed)": "%.4f"})
    if not suit["ok"]:
        st.info("VAR is not suitable for this configuration. Seasonal Naive or SARIMAX can still be used.")
        st.stop()
else:
    st.info("Seasonal Naive repeats the value observed in the same quarter one season earlier. Intervals use the "
            "RMSE of seasonal differences, widened by √k for k seasons ahead.")

result, err = state.get_forecast(ctx, model)
if result is None:
    st.error(f"The model could not produce a forecast: {err}")
    st.info("Try a simpler specification, a longer date range, or another model.")
    st.stop()

fcast = result.forecast
history = ctx.quarterly[target].dropna()
conv = {True: "Converged", False: "Not converged", None: "n/a"}[result.converged]
ui.kpi_row([
    ui.kpi_card("Model", result.model, result.spec, accent=True),
    ui.kpi_card("Observations used", str(result.n_obs), f"{quarter_label(history.index.min())} – {quarter_label(history.index.max())}"),
    ui.kpi_card("AIC / BIC", f"{fmt_number(result.aic, 1)}" if pd.notna(result.aic) else "–",
                f"BIC {fmt_number(result.bic, 1)}" if pd.notna(result.bic) else "Not likelihood-based"),
    ui.kpi_card("Convergence", conv, f"First forecast: {quarter_label(fcast.index[0])}"),
], 4)
if model == fc.VAR_MODEL:
    st.caption("VAR AIC/BIC are on the transformed multivariate scale and are not comparable with SARIMAX values.")
for w in result.warnings:
    st.warning(w)
for note in result.notes:
    st.info(note)

ui.section("Forecast")
show_fit = st.toggle("Show in-sample fitted values", value=False, key="lab_show_fit")
ui.chart(viz.forecast_chart(history, fcast, f"Historical {LABELS[target]} and Future Forecast", result.ci_level,
                            fitted=result.fitted if show_fit else None, y_title=y_title,
                            color=MODEL_COLORS.get(result.model), subtitle=result.spec))

table = fcast.reset_index()
table.insert(1, "Period", [quarter_label(d) for d in table["Date"]])
table = table.rename(columns={"Lower": f"Lower {result.ci_level}%", "Upper": f"Upper {result.ci_level}%"})
c1, c2 = st.columns([3, 2])
with c1:
    ui.table(table, number_format={c: "localized" for c in ["Forecast", f"Lower {result.ci_level}%", f"Upper {result.ci_level}%"]})
    st.download_button("Download forecast (CSV)", table.to_csv(index=False, date_format="%Y-%m-%d").encode(),
                       f"forecast_{target}_{result.model.replace(' ', '_').lower()}.csv", "text/csv",
                       icon=":material/download:")
with c2:
    st.markdown("**Parameters**")
    params = pd.DataFrame({"Parameter": list(result.params), "Value": [str(round(v, 6)) if isinstance(v, float) else str(v)
                                                                       for v in result.params.values()]})
    ui.table(params, height=260)
st.caption(f"{result.ci_level}% prediction intervals express model-based uncertainty under the model's assumptions; "
           "they are not guarantees of future traffic.")

ui.section("Actual vs fitted", "One-step in-sample fitted values on the original scale.")
fit = pd.DataFrame({"Actual": history, "Fitted": result.fitted.reindex(history.index)})
fig = go.Figure([
    go.Scatter(x=fit.index, y=fit["Actual"], name="Actual", mode="lines+markers", line=dict(color=COLORS["text"], width=2.2)),
    go.Scatter(x=fit.index, y=fit["Fitted"], name="In-sample fitted", mode="lines+markers",
               line=dict(color=MODEL_COLORS.get(result.model, COLORS["primary"]), width=2, dash="dash")),
])
viz.apply_theme(fig, f"Actual vs In-sample Fitted {LABELS[target]}", "Quarter", y_title, viz.HEIGHT_SECONDARY)
fig.update_yaxes(tickformat="~s")
ui.chart(fig)

if result.summary:
    with st.expander("Full statsmodels summary"):
        st.code(result.summary, language=None)
