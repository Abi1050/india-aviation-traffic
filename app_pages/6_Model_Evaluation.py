import pandas as pd
import streamlit as st

from config import settings
from config.settings import LABELS
from src import artifacts, evaluation as ev, forecasting as fc, state, ui, visualization as viz
from src.utils import fmt_number, fmt_pct, get_logger, quarter_label

log = get_logger(__name__)
ctx = state.get_context()
ui.no_data_stop(ctx)
ui.page_header("Model Evaluation & Comparison",
               "Leakage-free, expanding-window rolling-origin evaluation on identical evaluation quarters.",
               eyebrow="Modelling")
n = int(ctx.quarterly.dropna().shape[0])

need = ev.min_train_required(st.session_state["ev_models"] or [fc.NAIVE], ctx.period, state.sarimax_config(),
                             state.var_config())
max_test = min(20, n - need)
if max_test >= 4:
    st.session_state["ev_test_size"] = int(min(max(4, st.session_state["ev_test_size"]), max_test))

ui.section("Evaluation settings")
with st.form("eval_form"):
    c1, c2, c3 = st.columns([3, 1, 1])
    c1.multiselect("Models to compare", fc.MODEL_NAMES, key="ev_models")
    if max_test > 4:
        c2.slider("Evaluation quarters", 4, max_test, key="ev_test_size",
                  help=f"Number of one-step forecasts from the end of the series (the selected models need at least "
                       f"{need} training quarters).")
    else:
        c2.markdown(f"**Evaluation quarters:** {st.session_state['ev_test_size']}")
        c2.caption(f"{n} quarters available; the selected models need {need} for training.")
    c3.selectbox("Rank models by", ev.METRICS, key="ev_metric")
    st.form_submit_button("Run evaluation", type="primary", icon=":material/play_arrow:")

with st.expander("How the evaluation works", expanded=False):
    st.markdown(
        "1. For each evaluation quarter *t*, every model is fitted on observations **strictly before** *t*.\n"
        "2. It forecasts quarter *t* (one step ahead) and the error **actual − predicted** is recorded.\n"
        "3. The training window grows by one quarter and the process repeats.\n\n"
        "No random splits are used and every model is scored on the same quarters. SARIMAX and VAR use the "
        "parameters from the Forecasting Laboratory.\n\n"
        f"**{fc.EXOG_CONDITIONAL}** – uses the *observed* {', '.join(LABELS[c] for c in fc.exog_columns_for(ctx.target))} "
        "of the evaluation quarter. It measures accuracy *when those values are known*, so it is **not** a genuine "
        "future forecast.\n\n"
        f"**{fc.EXOG_OPERATIONAL}** – uses only information available at the forecast origin: each regressor is "
        "projected with Seasonal Naive. This mimics real forecasting.")

result, err = state.get_evaluation(ctx)
if result is None:
    st.error(f"Evaluation could not run: {err}")
    st.stop()
metric = st.session_state["ev_metric"]
metrics = result["metrics"]
best = ev.best_model(metrics, metric)
if fc.VAR_MODEL in st.session_state["ev_models"] and fc.VAR_MODEL not in result["models"]:
    st.warning("VAR was skipped because the target is not among the VAR variables.")

ui.kpi_row([
    ui.kpi_card("Evaluation period", result["period_label"], f"{result['n_common']} one-step forecasts per model",
                accent=True),
    ui.kpi_card("First training window", f"{result['first_train_size']} quarters", "Expands by one each step"),
    ui.kpi_card("Best model", best or "–", f"Lowest {metric}"),
    ui.kpi_card(f"Best {metric}", fmt_pct(metrics.set_index('Model').loc[best, metric], 2, False) if best and "%" in metric
                else fmt_number(metrics.set_index('Model').loc[best, metric]) if best else "–", LABELS[ctx.target]),
], 4)
if not result["failures"].empty:
    st.warning(f"{len(result['failures'])} model fit(s) failed; metrics use only quarters where every model "
               "produced a forecast.")
    ui.table(result["failures"])

ui.section("Comparison table", "Lower is better for every metric. MAPE excludes quarters with zero actual traffic "
           "(MAPE N shows how many were used). Bias = mean of actual − predicted.")
ui.table(metrics.sort_values(metric), number_format={"MAE": "localized", "RMSE": "localized", "MAPE (%)": "%.2f",
                                                     "sMAPE (%)": "%.2f", "Bias (mean error)": "localized"})

c1, c2, c3 = st.columns(3)
for col, m in zip((c1, c2, c3), ["MAE", "RMSE", "MAPE (%)"]):
    with col:
        ui.chart(viz.metric_bars(metrics, m, f"Model Performance by {m.replace(' (%)', '')}", height=300))

ui.section("Actual vs predicted")
history = ctx.quarterly[ctx.target].loc[:result["forecasts"].index.min()]
ui.chart(viz.actual_vs_predicted(result["forecasts"], result["models"], f"Actual vs Predicted {LABELS[ctx.target]}",
                                 history=history.iloc[-12:],
                                 y_title="Passengers" if ctx.target.startswith("Pax") else "Freight (source units)"))

ui.section("Per-quarter forecast errors", "Rolling forecast errors (actual − predicted); these are not model residuals.")
errors = result["errors"]
c1, c2 = st.columns([3, 2])
with c1:
    ui.chart(viz.error_bars(errors, "Forecast Error by Quarter"))
with c2:
    ui.chart(viz.error_distribution(errors, "Forecast Error Distribution"))
pivot = errors.pivot_table(index="Date", columns="Model", values="Error").reset_index()
pivot.insert(1, "Period", [quarter_label(d) for d in pivot["Date"]])
pivot = pivot.merge(result["forecasts"][["Actual", "Train size"]], left_on="Date", right_index=True)
ui.table(pivot, number_format={m: "localized" for m in result["models"]} | {"Actual": "localized"})

ui.section("Interpretation")
lines = []
ranked = metrics.sort_values(metric).reset_index(drop=True)
if best:
    lines.append(f"{best} ranks first by {metric} over {result['period_label']}.")
    if fc.NAIVE in ranked["Model"].values and best != fc.NAIVE:
        base = ranked.set_index("Model").loc[fc.NAIVE]
        top = ranked.set_index("Model").loc[best]
        lines.append(f"Relative to the Seasonal Naive baseline, {best} reduces MAE by "
                     f"{(1 - top['MAE'] / base['MAE']) * 100:.1f}% and RMSE by {(1 - top['RMSE'] / base['RMSE']) * 100:.1f}%.")
    elif best == fc.NAIVE:
        lines.append("No model beats the Seasonal Naive baseline here, so the added complexity is not justified "
                     "for these evaluation quarters.")
    rank_by = {m: ranked.sort_values(m)["Model"].iloc[0] for m in ["MAE", "RMSE", "MAPE (%)"]}
    if len(set(rank_by.values())) > 1:
        lines.append("The ranking depends on the metric: " + ", ".join(f"{k} → {v}" for k, v in rank_by.items()) + ".")
    for _, row in metrics.iterrows():
        if abs(row["Bias (mean error)"]) > 0.5 * row["MAE"]:
            lines.append(f"{row['Model']} errors are mostly one-sided ("
                         + ("under" if row["Bias (mean error)"] > 0 else "over") + "-prediction on average).")
if fc.EXOG_CONDITIONAL in metrics["Model"].values:
    lines.append(f"{fc.EXOG_CONDITIONAL} uses observed regressor values from each evaluation quarter, so its accuracy "
                 "is an upper bound and is excluded when choosing the future-forecast model.")
lines.append(f"With only {result['n_common']} evaluation quarters, differences between close models may not be "
             "statistically meaningful.")
ui.insights(lines)

# --------------------------------------------------------------------------- save outputs
signature = (tuple(result["models"]), result["test_size"], result["period_label"], state.sarimax_config().label(),
             state.var_config().label(), ctx.filter_note, ctx.target)
if st.session_state.get("ev_saved") != signature:
    try:
        settings.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        result["forecasts"].to_csv(settings.EXPORT_DIR / "rolling_origin_forecasts.csv", date_format="%Y-%m-%d")
        metrics.to_csv(settings.EXPORT_DIR / "rolling_origin_metrics.csv", index=False)
        errors.to_csv(settings.EXPORT_DIR / "rolling_origin_errors.csv", index=False, date_format="%Y-%m-%d")
        st.session_state["ev_saved"] = signature
    except OSError as exc:
        log.error("Could not save evaluation outputs: %s", exc)
        st.warning(f"Evaluation outputs could not be saved to {settings.EXPORT_DIR}: {exc}")
st.caption(f"Evaluation outputs saved to `{settings.EXPORT_DIR}` (the notebook's own files are not modified).")
c1, c2 = st.columns(2)
c1.download_button("Download model comparison (CSV)", metrics.to_csv(index=False).encode(), "model_comparison_rolling.csv",
                   "text/csv", icon=":material/download:")
c2.download_button("Download rolling forecasts (CSV)", result["forecasts"].to_csv(date_format="%Y-%m-%d").encode(),
                   "rolling_origin_forecasts.csv", "text/csv", icon=":material/download:")

# --------------------------------------------------------------------------- SARIMAX screening
with st.expander("SARIMAX configuration screening"):
    st.caption("Compares several SARIMAX orders on the same rolling evaluation quarters. Choosing the best order "
               "on the evaluation period makes its score optimistic; treat this as exploratory.")
    candidates = [((1, 1, 0), (0, 1, 0)), ((0, 1, 1), (0, 1, 0)), ((0, 1, 0), (0, 1, 0)), ((1, 1, 1), (1, 1, 0)),
                  ((0, 1, 1), (0, 1, 1)), ((1, 1, 0), (1, 1, 0))]
    if st.button("Run screening", icon=":material/tune:"):
        configs = tuple(fc.SarimaxConfig(o, (*so, ctx.period), bool(st.session_state["cfg_log"])) for o, so in candidates)
        with st.spinner(f"Screening {len(configs)} configurations…"):
            st.session_state["ev_screen"] = state.cached_screening(ctx.quarterly.dropna(), ctx.target, configs,
                                                                   result["test_size"], ctx.period)
    if "ev_screen" in st.session_state:
        ui.table(st.session_state["ev_screen"], number_format={"MAE": "localized", "RMSE": "localized",
                                                               "MAPE (%)": "%.2f", "sMAPE (%)": "%.2f",
                                                               "Bias (mean error)": "localized"})

with st.expander("Results saved earlier by the notebook"):
    st.caption("Read-only copies from the outputs folder, shown for comparison with the live results above.")
    found = False
    for name in ["rolling_three_model_comparison.csv", "final_validation_metrics.csv", "sarimax_configuration_comparison.csv"]:
        df = artifacts.read_csv(name)
        if df is not None:
            found = True
            st.markdown(f"**{name}** – {settings.ARTIFACT_DESCRIPTIONS.get(name, '')}")
            st.dataframe(df, width="stretch", hide_index=True)
    if not found:
        st.info("No saved notebook comparison files were found.")
