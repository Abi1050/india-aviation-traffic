import pandas as pd
import streamlit as st

from config.settings import LABELS, MODEL_COLORS
from src import diagnostics as dg, forecasting as fc, state, ui, visualization as viz
from src.utils import fmt_number

ctx = state.get_context()
ui.no_data_stop(ctx)
ui.page_header("Residual Analysis & Model Diagnostics",
               "In-sample residuals of fitted models and, separately, out-of-sample rolling forecast errors.",
               eyebrow="Modelling")


def diagnostics_block(values: pd.Series, label: str, unit: str, key: str, model_df: int = 0) -> None:
    values = values.dropna()
    summary = dg.residual_summary(values)
    note = dg.small_sample_note(summary["N"])
    lb = None
    try:
        lb = dg.ljung_box(values, [4, 8], model_df=model_df)
    except ValueError as exc:
        st.info(f"Ljung-Box test not computed: {exc}")
    lb_p = lb["p-value"].iloc[0] if lb is not None else None
    ui.kpi_row([
        ui.kpi_card("Observations", str(summary["N"]), label, accent=True),
        ui.kpi_card("Mean", fmt_number(summary["Mean"], 4 if abs(summary["Mean"]) < 10 else 0),
                    f"t-test p = {summary.get('Mean = 0 t-test p-value', float('nan')):.3f}"),
        ui.kpi_card("Standard deviation", fmt_number(summary["Std. dev."], 4 if summary["Std. dev."] < 10 else 0), unit),
        ui.kpi_card("Ljung-Box p (lag " + (str(int(lb["Lag"].iloc[0])) if lb is not None else "–") + ")",
                    f"{lb_p:.3f}" if lb_p is not None else "–",
                    "≥ 0.05: no evidence of autocorrelation" if lb_p is not None and lb_p >= 0.05 else
                    "< 0.05: autocorrelation remains" if lb_p is not None else "Not computed"),
    ], 4)
    if note:
        st.warning(note)
    color = MODEL_COLORS.get(label.split(" – ")[0])
    c1, c2 = st.columns(2)
    with c1:
        ui.chart(viz.residual_series_chart(values, f"{label} Over Time", unit, color=color))
    with c2:
        ui.chart(viz.histogram(values, f"{label} – Distribution", unit, color=color,
                               nbins=min(15, max(5, summary["N"] // 2))))
    c1, c2 = st.columns(2)
    with c1:
        if summary["N"] >= 3:
            ui.chart(viz.qq_chart(dg.qq_points(values), f"{label} – Normal Q-Q Plot"))
    with c2:
        try:
            ui.chart(viz.correlogram(dg.acf_pacf(values), "ACF", f"{label} – Autocorrelation"))
        except ValueError as exc:
            st.info(f"Autocorrelation not computed: {exc}")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Diagnostic summary**")
        ui.table(pd.DataFrame({"Statistic": list(summary), "Value": [f"{v:,.4f}" if isinstance(v, float) else str(v)
                                                                     for v in summary.values()]}))
    with c2:
        if lb is not None:
            st.markdown("**Ljung-Box test** (H0: no autocorrelation up to the lag)")
            ui.table(lb, number_format={"Q statistic": "%.3f", "p-value": "%.4f"})
        st.caption("Shapiro-Wilk and Jarque-Bera test normality (H0: normal). With small samples these tests have "
                   "low power; a non-significant result does not prove normality.")


tab_in, tab_roll = st.tabs(["In-sample model residuals", "Rolling forecast errors (actual − predicted)"])

with tab_in:
    st.caption("Residuals of a model fitted to every selected quarter. They show how well the model describes the "
               "data it was fitted on, not how well it forecasts.")
    model = st.selectbox("Fitted model", [fc.SARIMAX, fc.EXOG_OPERATIONAL, fc.VAR_MODEL, fc.NAIVE], key="ra_model")
    result, err = state.get_forecast(ctx, model)
    if result is None:
        st.error(f"Model could not be fitted: {err}")
    else:
        st.markdown(f"**{result.spec}** – residual scale: {result.residual_scale}.")
        for note in result.notes:
            st.info(note)
        for w in result.warnings:
            if "stable" in w:
                st.warning(w)
        k = 0
        if model in (fc.SARIMAX, fc.EXOG_OPERATIONAL):
            cfg = state.sarimax_config()
            k = cfg.order[0] + cfg.order[2] + cfg.seasonal_order[0] + cfg.seasonal_order[2]
        diagnostics_block(result.residuals, f"{result.model} – In-sample Residuals", result.residual_scale, "in", k)

with tab_roll:
    st.caption("Out-of-sample errors from the rolling-origin evaluation: each forecast was made using only earlier "
               "quarters. These are forecast errors, not fitted-model residuals.")
    evaluation, err = state.get_evaluation(ctx)
    if evaluation is None:
        st.error(f"Evaluation unavailable: {err}")
    else:
        model = st.selectbox("Evaluated model", evaluation["models"], key="ra_eval_model")
        e = (evaluation["forecasts"]["Actual"] - evaluation["forecasts"][model]).rename("Error")
        st.markdown(f"Evaluation period **{evaluation['period_label']}** · target {LABELS[ctx.target]}.")
        diagnostics_block(e, f"{model} – Rolling Forecast Errors", "Actual − predicted", "roll")
