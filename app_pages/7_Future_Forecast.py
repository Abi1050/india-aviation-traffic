import json

import numpy as np
import pandas as pd
import streamlit as st

from config.settings import LABELS, MODEL_COLORS
from src import forecasting as fc, report_context, reporting, state, ui, visualization as viz
from src.utils import fmt_number, fmt_pct, quarter_label, safe_pct_change

ctx = state.get_context()
ui.no_data_stop(ctx)
target_label = LABELS[ctx.target]
ui.page_header("Future Forecast", f"{ctx.horizon}-quarter outlook for {target_label} with prediction intervals.",
               eyebrow="Modelling")

c1, c2 = st.columns([2, 1])
c1.selectbox("Forecast model", [state.BEST, *fc.FUTURE_CAPABLE], key="ff_model",
             help="'Best' picks the lowest-error model from the Model Evaluation settings, excluding the conditional "
                  "exogenous variant, which needs observed future regressors.")
c2.toggle("Show lower bounds truncated at zero", key="ff_clip",
          help="Display-only: negative lower bounds are impossible for traffic, so they can be shown as 0. "
               "The estimated values are kept in the downloads with a separate column.")

result, model, reason, err = report_context.future_forecast(ctx)
if result is None:
    st.error(f"Forecast unavailable: {err}")
    st.stop()

history = ctx.quarterly[ctx.target].dropna()
fcst = result.forecast.copy()
clip = bool(st.session_state["ff_clip"])
display = fcst.copy()
if clip:
    display["Lower"] = display["Lower"].clip(lower=0)
st.caption(f"Model: **{result.spec}** — {reason} Data: {ctx.filter_note}. Forecast starts after the last observed "
           f"quarter ({quarter_label(history.index[-1])}).")

w1 = fcst["Upper"].iloc[0] - fcst["Lower"].iloc[0]
wH = fcst["Upper"].iloc[-1] - fcst["Lower"].iloc[-1]
ui.kpi_row([
    ui.kpi_card("First forecast quarter", quarter_label(fcst.index[0]), fmt_number(fcst["Forecast"].iloc[0]), accent=True),
    ui.kpi_card("Last forecast quarter", quarter_label(fcst.index[-1]), fmt_number(fcst["Forecast"].iloc[-1])),
    ui.kpi_card("Average quarterly forecast", fmt_number(fcst["Forecast"].mean(), compact=True),
                f"Last 4 observed quarters averaged {fmt_number(history.iloc[-4:].mean(), compact=True)}"),
    ui.kpi_card("Interval width", f"{fmt_number(w1, compact=True)} → {fmt_number(wH, compact=True)}",
                f"{ctx.ci}% interval, first vs last quarter"),
], 4)
for w in result.warnings:
    st.warning(w)
for note in result.notes:
    st.caption(note)

ui.chart(viz.forecast_chart(history, display, f"Historical {target_label} and Future Forecast", result.ci_level,
                            y_title="Passengers" if ctx.target.startswith("Pax") else "Freight (source units)",
                            color=MODEL_COLORS.get(result.model),
                            subtitle=f"{result.ci_level}% prediction interval · {result.spec}"
                                     + (" · lower bounds shown truncated at 0" if clip and (fcst['Lower'] < 0).any() else "")),
         filename=f"future_forecast_{ctx.target}")

# --------------------------------------------------------------------------- table
ui.section("Forecast table")
table = pd.DataFrame({
    "Date": fcst.index, "Period": [quarter_label(d) for d in fcst.index], "Point forecast": fcst["Forecast"].values,
    f"Lower {result.ci_level}%": display["Lower"].values, f"Upper {result.ci_level}%": fcst["Upper"].values,
})
table["Interval width"] = fcst["Upper"].values - fcst["Lower"].values
table["Width (% of forecast)"] = np.where(fcst["Forecast"].values > 0, table["Interval width"] / fcst["Forecast"].values * 100,
                                          np.nan)
if clip:
    table["Lower (estimated)"] = fcst["Lower"].values
ui.table(table, number_format={c: "localized" for c in ["Point forecast", f"Lower {result.ci_level}%",
                                                        f"Upper {result.ci_level}%", "Interval width", "Lower (estimated)"]}
         | {"Width (% of forecast)": "%.1f"})
if clip and (fcst["Lower"] < 0).any():
    st.caption("Lower bounds below zero are displayed as 0; 'Lower (estimated)' keeps the model's actual values.")

# --------------------------------------------------------------------------- interpretation
ui.section("Forecast interpretation")
f = fcst["Forecast"]
slope = np.polyfit(np.arange(len(f)), f.values, 1)[0] if len(f) > 1 else 0.0
change = safe_pct_change(f.iloc[-1], history.iloc[-1])
yoy_like = safe_pct_change(f.iloc[:4].sum(), history.iloc[-4:].sum()) if len(f) >= 4 and len(history) >= 4 else np.nan
lines = [
    f"The point forecast trends {'upward' if slope > 0 else 'downward' if slope < 0 else 'flat'} across the horizon "
    f"(linear slope {fmt_number(slope)} per quarter); the last forecast is {fmt_pct(change)} versus the last observed "
    f"quarter ({quarter_label(history.index[-1])})."
]
if not np.isnan(yoy_like):
    lines.append(f"The first four forecast quarters total {fmt_number(f.iloc[:4].sum(), compact=True)}, "
                 f"{fmt_pct(yoy_like)} compared with the last four observed quarters.")
if len(f) >= 4:
    by_q = f.groupby(f.index.quarter).mean()
    spread = safe_pct_change(by_q.max(), by_q.min())
    lines.append(f"Quarterly variation is {'present' if spread > 3 else 'small'}: forecasts peak in Q{int(by_q.idxmax())} "
                 f"and are lowest in Q{int(by_q.idxmin())} (difference {fmt_pct(spread, signed=False)}).")
lines.append(f"Uncertainty grows with the horizon: the {result.ci_level}% interval widens from {fmt_number(w1, compact=True)} "
             f"in {quarter_label(fcst.index[0])} to {fmt_number(wH, compact=True)} in {quarter_label(fcst.index[-1])}.")
lines.append("These are model-based estimates conditional on past patterns continuing; they are not guaranteed future "
             "traffic, and shocks such as the 2020 disruption are not anticipated by the model.")
ui.insights(lines)

# --------------------------------------------------------------------------- validation
ui.section("Forecast validation")
checks = fc.validate_forecast(fcst, history.index, ctx.horizon)
ui.table(checks)
failed = checks[~checks["Passed"]]
if failed.empty:
    st.success("All validation checks passed.")
else:
    st.warning("Checks not passed: " + "; ".join(failed["Check"]) + ". Values are reported as estimated, not altered.")

# --------------------------------------------------------------------------- downloads
ui.section("Downloads")
csv = table.to_csv(index=False, date_format="%Y-%m-%d").encode()
summary = {"target": ctx.target, "model": result.model, "specification": result.spec, "selection_reason": reason,
           "confidence_level": result.ci_level, "horizon": ctx.horizon, "first_quarter": quarter_label(fcst.index[0]),
           "last_quarter": quarter_label(fcst.index[-1]), "last_observed": quarter_label(history.index[-1]),
           "data_selection": ctx.filter_note, "interpretation": lines, "warnings": result.warnings,
           "checks": checks.to_dict(orient="records"),
           "forecast": json.loads(table.to_json(orient="records", date_format="iso"))}
c1, c2, c3, c4 = st.columns(4)
c1.download_button("Forecast (CSV)", csv, f"future_forecast_{ctx.target}.csv", "text/csv", icon=":material/table:")
c2.download_button("Summary (JSON)", json.dumps(summary, indent=2, default=str).encode(), "future_forecast_summary.json",
                   "application/json", icon=":material/data_object:")
try:
    png = reporting.chart_forecast(history, fcst, result.ci_level, f"{target_label}: {ctx.horizon}-Quarter Forecast",
                                   "Passengers" if ctx.target.startswith("Pax") else "Freight (source units)")
    c3.download_button("Chart (PNG)", png, f"future_forecast_{ctx.target}.png", "image/png", icon=":material/image:")
except Exception as exc:  # noqa: BLE001
    png = None
    c3.warning(f"PNG export failed: {exc}")
signature = (result.spec, ctx.filter_note, ctx.ci, tuple(np.round(fcst["Forecast"].values, 3)))
if c4.button("Build PDF report", icon=":material/picture_as_pdf:"):
    with st.spinner("Building PDF…"):
        data = report_context.assemble(ctx)
        charts = {"future_forecast.png": png} if png else {}
        st.session_state["ff_pdf"] = (signature, reporting.pdf_report(data, charts, [] if png else ["future_forecast.png"],
                                                                      forecast_only=True))
if st.session_state.get("ff_pdf", (None,))[0] == signature:
    c4.download_button("Download PDF", st.session_state["ff_pdf"][1], "future_forecast_report.pdf", "application/pdf",
                       icon=":material/download:", type="primary")
st.caption("The interactive chart can also be saved as PNG with the camera icon in its toolbar.")
