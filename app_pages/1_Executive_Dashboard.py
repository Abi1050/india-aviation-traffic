import pandas as pd
import streamlit as st

from config.settings import FREIGHT_COLUMNS, LABELS, PASSENGER_COLUMNS, TRAFFIC_COLUMNS
from src import eda, evaluation as ev, forecasting as fc, state, ui, visualization as viz
from src.utils import fmt_number, fmt_pct, quarter_label, safe_pct_change

ctx = state.get_context()
ui.no_data_stop(ctx)
ui.page_header("Civil Aviation Analytics & Forecasting",
               "Interactive analysis and forecasting of international passenger and freight traffic involving India.",
               eyebrow="Executive Dashboard")

q = ctx.quarterly.dropna(how="all")
latest = q.index.max()
year_ago = latest - pd.DateOffset(years=1)
latest_info = ctx.bundle.latest
st.caption(f"Showing {ctx.filter_note}. Values are in the source dataset's units.")
if latest_info.get("date") == latest and not latest_info.get("complete", True):
    st.warning(f"{quarter_label(latest)} may be incomplete: " + " ".join(latest_info.get("concerns", [])))


def latest_card(col: str, label: str) -> str:
    value = q[col].iloc[-1]
    if year_ago in q.index:
        yoy = safe_pct_change(value, q.loc[year_ago, col])
        return ui.kpi_card(label, fmt_number(value, compact=True), f"YoY vs {quarter_label(year_ago)}",
                           fmt_pct(yoy), ui.tone_for(yoy))
    return ui.kpi_card(label, fmt_number(value, compact=True), f"{quarter_label(latest)} · no prior-year quarter")


evaluation, eval_error = state.get_evaluation(ctx)
metric = st.session_state["ev_metric"]
best = ev.best_model(evaluation["metrics"], metric) if evaluation else None

cards = [
    ui.kpi_card("Total passengers to India", fmt_number(q["PaxToIndia"].sum(), compact=True),
                f"Sum of {len(q)} quarters, {quarter_label(q.index.min())}–{quarter_label(latest)}", accent=True),
    latest_card("PaxToIndia", f"Passengers to India · {quarter_label(latest)}"),
    latest_card("PaxFromIndia", f"Passengers from India · {quarter_label(latest)}"),
    latest_card("FreightToIndia", f"Freight to India · {quarter_label(latest)}"),
    latest_card("FreightFromIndia", f"Freight from India · {quarter_label(latest)}"),
]
if len(q) >= 8:
    last4, prev4 = q["PaxToIndia"].iloc[-4:].sum(), q["PaxToIndia"].iloc[-8:-4].sum()
    growth = safe_pct_change(last4, prev4)
    cards.append(ui.kpi_card("Passenger growth, last 4 quarters", fmt_pct(growth),
                             f"{quarter_label(q.index[-4])}–{quarter_label(latest)} vs "
                             f"{quarter_label(q.index[-8])}–{quarter_label(q.index[-5])}", tone=ui.tone_for(growth)))
else:
    cards.append(ui.kpi_card("Passenger growth, last 4 quarters", "–", "Needs at least 8 quarters"))
if best:
    row = evaluation["metrics"].set_index("Model").loc[best]
    value = fmt_pct(row[metric], 2, signed=False) if "%" in metric else fmt_number(row[metric])
    cards.append(ui.kpi_card("Best evaluated model", best,
                             f"{metric} {value} · {evaluation['n_common']} rolling 1-step forecasts, "
                             f"{evaluation['period_label']}"))
else:
    cards.append(ui.kpi_card("Best evaluated model", "–", eval_error or "No evaluation available"))
future = fc.future_index(latest, ctx.horizon)
cards.append(ui.kpi_card("Forecast horizon", f"{ctx.horizon} quarters",
                         f"{quarter_label(future[0])} – {quarter_label(future[-1])} · {LABELS[ctx.target]}"))
ui.kpi_row(cards, 4)

ui.section("Traffic trends")
c1, c2 = st.columns(2)
with c1:
    ui.chart(viz.line_chart(q, PASSENGER_COLUMNS, "Passenger Traffic: To vs From India", ctx.markers))
with c2:
    ui.chart(viz.line_chart(q, FREIGHT_COLUMNS, "Freight Traffic: To vs From India", ctx.markers))

c1, c2 = st.columns(2)
with c1:
    ui.chart(viz.seasonal_comparison_chart(eda.seasonal_profile(q, "PaxToIndia"),
                                           "Quarterly Passenger Traffic to India by Year", "Passengers"))
with c2:
    complete = q[TRAFFIC_COLUMNS].dropna()
    ui.chart(viz.heatmap(eda.correlation_matrix(complete, TRAFFIC_COLUMNS), "Passenger and Freight Correlation"))

ui.section("Forecast model performance",
           f"Expanding-window, one-step-ahead evaluation of {LABELS[ctx.target]}. Configure on the Model Evaluation page.")
if evaluation:
    c1, c2 = st.columns([3, 2])
    with c1:
        ui.chart(viz.actual_vs_predicted(evaluation["forecasts"], evaluation["models"],
                                         f"Actual vs Predicted {LABELS[ctx.target]}",
                                         y_title="Passengers" if ctx.target.startswith("Pax") else "Freight (source units)"))
    with c2:
        ui.chart(viz.metric_bars(evaluation["metrics"], metric, f"Model Performance by {metric}", height=450))
else:
    st.warning(f"Model evaluation unavailable: {eval_error}")

ui.section("Key observations", "Generated from the filtered data; they describe patterns, not causes.")
lines = eda.series_insights(q, "PaxToIndia")
if best:
    ranked = evaluation["metrics"].sort_values(metric)
    others = ", ".join(f"{m} ({fmt_pct(v, 2, False) if '%' in metric else fmt_number(v)})"
                       for m, v in zip(ranked["Model"].iloc[1:], ranked[metric].iloc[1:]))
    lines.append(f"By {metric}, {best} has the lowest rolling one-step error"
                 + (f"; followed by {others}." if others else "."))
ui.insights(lines)
