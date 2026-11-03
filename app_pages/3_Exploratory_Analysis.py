import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.settings import (FREIGHT_COLUMNS, LABELS, PASSENGER_COLUMNS, SERIES_COLORS, SERIES_TITLES,
                             TRAFFIC_COLUMNS, UNITS)
from src import eda, state, ui, visualization as viz
from src.utils import fmt_number, quarter_label

ctx = state.get_context()
ui.no_data_stop(ctx)
ui.page_header("Exploratory Data Analysis",
               "Trends, growth, seasonality, distributions and relationships between the four traffic series.",
               eyebrow="Data & analysis")
q = ctx.quarterly
st.caption(f"Showing {ctx.filter_note}. Passenger values are passenger counts; freight values use the source's "
           "units, which the source repository does not document.")

tabs = st.tabs(["Passenger traffic", "Freight traffic", "Statistical summary", "Correlation",
                "Seasonal decomposition"] + (["Country breakdown"] if ctx.bundle.has_country else []))


def category_tab(columns: list[str], noun: str, y_title: str, key: str) -> None:
    a, b = columns
    c1, c2 = st.columns([2, 1])
    ma = c2.selectbox("Moving average", [None, 2, 4, 8], index=2, key=f"{key}_ma",
                      format_func=lambda v: "None" if v is None else f"{v} quarters")
    c1.markdown(f"**{noun} variables:** {LABELS[a]} and {LABELS[b]}")
    c1, c2 = st.columns(2)
    with c1:
        ui.chart(viz.line_chart(q, [a], SERIES_TITLES[a], ctx.markers, y_title, viz.HEIGHT_SECONDARY, moving_average=ma))
    with c2:
        ui.chart(viz.line_chart(q, [b], SERIES_TITLES[b], ctx.markers, y_title, viz.HEIGHT_SECONDARY, moving_average=ma))
    ui.chart(viz.line_chart(q, [a, b], f"{noun} Traffic: Inbound vs Outbound Comparison", ctx.markers, y_title))

    ui.section(f"{noun} growth", "Percentage change against the previous quarter and the same quarter one year earlier.")
    var = st.radio("Growth variable", [a, b], horizontal=True, format_func=lambda c: LABELS[c], key=f"{key}_gvar")
    g = eda.growth_table(q[var])
    c1, c2 = st.columns(2)
    with c1:
        ui.chart(viz.growth_chart(g["QoQ change (%)"], f"Quarterly {noun} Growth – {LABELS[var]}", g["Small base"]))
    with c2:
        ui.chart(viz.growth_chart(g["YoY change (%)"], f"Year-over-Year {noun} Growth – {LABELS[var]}", g["Small base"]))
    if g["Small base"].any():
        st.caption("Growth rates measured from quarters below a quarter of the median level (e.g. 2020–2021) are "
                   "flagged in amber; their size reflects the small base, not unusually strong demand.")

    ui.section(f"Annual {noun.lower()} summary")
    annual = eda.annual_summary(q, columns)
    c1, c2 = st.columns([3, 2])
    with c1:
        fig = go.Figure()
        for col in columns:
            fig.add_trace(go.Bar(x=annual["Year"], y=annual[col], name=LABELS[col], marker_color=SERIES_COLORS[col],
                                 hovertemplate="%{x}: %{y:,.0f}<extra>" + LABELS[col] + "</extra>"))
        viz.apply_theme(fig, f"Annual {noun} Traffic", "Year", y_title,
                        subtitle="Years with fewer than four observed quarters are partial totals")
        fig.update_layout(barmode="group", hovermode="x unified")
        fig.update_yaxes(tickformat="~s")
        ui.chart(fig)
    with c2:
        ui.table(annual, height=380)
    partial = annual.loc[~annual["Complete year"], "Year"].tolist()
    if partial:
        st.caption(f"Partial years (fewer than 4 quarters in the selection): {', '.join(map(str, partial))}.")

    ui.section(f"Quarterly {noun.lower()} seasonality")
    var = st.radio("Seasonality variable", [a, b], horizontal=True, format_func=lambda c: LABELS[c], key=f"{key}_svar")
    prof = eda.seasonal_profile(q, var)
    c1, c2 = st.columns(2)
    with c1:
        ui.chart(viz.seasonal_comparison_chart(prof, f"Quarterly Seasonal Comparison – {LABELS[var]}", y_title))
    with c2:
        ui.chart(viz.quarter_box_chart(prof, f"Distribution by Quarter of Year – {LABELS[var]}", y_title))


with tabs[0]:
    category_tab(PASSENGER_COLUMNS, "Passenger", "Passengers", "pax")
    ui.insights(eda.series_insights(q, "PaxToIndia"))

with tabs[1]:
    category_tab(FREIGHT_COLUMNS, "Freight", "Freight (source units)", "frt")
    ui.insights(eda.series_insights(q, "FreightToIndia"))

with tabs[2]:
    ui.section("Analysis settings")
    var = st.selectbox("Traffic variable", TRAFFIC_COLUMNS, format_func=lambda c: LABELS[c], key="eda_stat_var")
    s = q[var].dropna()
    ui.kpi_row([
        ui.kpi_card("Mean", fmt_number(s.mean(), compact=True), UNITS[var], accent=True),
        ui.kpi_card("Median", fmt_number(s.median(), compact=True), UNITS[var]),
        ui.kpi_card("Standard deviation", fmt_number(s.std(), compact=True), f"CV {s.std() / s.mean() * 100:.1f}%"),
        ui.kpi_card("Minimum", fmt_number(s.min(), compact=True), quarter_label(s.idxmin())),
        ui.kpi_card("Maximum", fmt_number(s.max(), compact=True), quarter_label(s.idxmax())),
    ], 5)
    c1, c2 = st.columns(2)
    unit_title = "Passengers" if var.startswith("Pax") else "Freight (source units)"
    with c1:
        fig = go.Figure(go.Box(y=s, name=LABELS[var], marker_color=SERIES_COLORS[var], boxpoints="all", jitter=0.35,
                               customdata=[quarter_label(i) for i in s.index],
                               hovertemplate="%{customdata}: %{y:,.0f}<extra></extra>"))
        viz.apply_theme(fig, f"{LABELS[var]} – Box Plot", None, unit_title, legend=False)
        fig.update_layout(hovermode="closest")
        ui.chart(fig)
    with c2:
        ui.chart(viz.histogram(s, f"{LABELS[var]} – Histogram", unit_title, SERIES_COLORS[var], nbins=15))
    ui.section("Statistical results", "All four variables, computed on quarterly totals.")
    stats_df = eda.descriptive_statistics(q, TRAFFIC_COLUMNS)
    ui.table(stats_df, number_format={c: "localized" for c in ["Mean", "Median", "Std. dev.", "Min", "Q1", "Q3", "Max"]}
             | {"Skewness": "%.3f", "Kurtosis": "%.3f", "CV (%)": "%.1f"})
    st.caption("Kurtosis is excess kurtosis (0 for a normal distribution). Skewness above 0 indicates a longer "
               "right tail.")
    row = stats_df.set_index("Variable").loc[var]
    shape = "right-skewed" if row["Skewness"] > 0.5 else "left-skewed" if row["Skewness"] < -0.5 else "roughly symmetric"
    ui.insights([f"{LABELS[var]} ranges from {fmt_number(row['Min'])} to {fmt_number(row['Max'])} with a median of "
                 f"{fmt_number(row['Median'])}; the distribution is {shape} (skewness {row['Skewness']:.2f}).",
                 f"The interquartile range is {fmt_number(row['Q1'])} – {fmt_number(row['Q3'])}."])

with tabs[3]:
    ui.section("Traffic variable correlation matrix",
               "Calculated on quarterly totals after country filtering and aggregation (not on country rows).")
    c1, c2 = st.columns(2)
    method = c1.radio("Method", ["pearson", "spearman"], horizontal=True, format_func=str.title, key="eda_corr_method")
    basis = c2.radio("Basis", ["Levels", "Quarter-over-quarter log changes"], horizontal=True, key="eda_corr_basis")
    data = q[TRAFFIC_COLUMNS].dropna()
    if basis != "Levels":
        data = np.log(data.where(data > 0)).diff().dropna()
    if len(data) < 3:
        st.warning("Too few complete quarters for correlation.")
    else:
        corr = eda.correlation_matrix(data, TRAFFIC_COLUMNS, method)
        c1, c2 = st.columns([3, 2])
        with c1:
            ui.chart(viz.heatmap(corr, f"Traffic Variable Correlation Matrix ({method.title()}, {basis.lower()})"))
        with c2:
            ui.table(corr.reset_index().rename(columns={"index": "Variable"}),
                     number_format={c: "%.3f" for c in TRAFFIC_COLUMNS})
            st.caption(f"Based on {len(data)} quarters.")
        ui.insights(eda.correlation_insights(corr))
        if basis == "Levels":
            st.caption("Tip: switch the basis to log changes to see whether the series move together quarter to quarter "
                       "rather than only sharing a long-run trend.")

with tabs[4]:
    ui.section("Seasonal decomposition", "Classical decomposition into trend, seasonal and residual components.")
    c1, c2 = st.columns(2)
    var = c1.selectbox("Traffic variable", TRAFFIC_COLUMNS, format_func=lambda c: LABELS[c], key="eda_dec_var")
    model = c2.radio("Decomposition model", ["additive", "multiplicative"], horizontal=True, format_func=str.title,
                     key="eda_dec_model")
    try:
        res = eda.decompose(q[var], ctx.period, model)
        ui.chart(viz.decomposition_chart(res, f"Seasonal Decomposition – {LABELS[var]} (period {ctx.period})"))
        resid, seas, trend = res.resid.dropna(), res.seasonal, res.trend
        if model == "additive":
            st_seas = max(0.0, 1 - resid.var() / (seas.loc[resid.index] + resid).var())
            st_trend = max(0.0, 1 - resid.var() / (trend.loc[resid.index] + resid).var())
        else:
            st_seas = max(0.0, 1 - np.log(resid).var() / np.log(seas.loc[resid.index] * resid).var())
            st_trend = max(0.0, 1 - np.log(resid).var() / np.log(trend.loc[resid.index] * resid).var())
        idx = seas.groupby(seas.index.quarter).first()
        fmt = (lambda v: f"{v:+,.0f}") if model == "additive" else (lambda v: f"{v:.3f}×")
        ui.insights([
            f"Strength of seasonality: {st_seas:.2f}; strength of trend: {st_trend:.2f} (0 = none, 1 = dominant; "
            "Wang–Smith–Hyndman measure).",
            "Seasonal indices – " + ", ".join(f"Q{k}: {fmt(v)}" for k, v in idx.items()) + ".",
            "The 2020–2021 disruption is absorbed partly by the trend and partly by large residuals; seasonal "
            "estimates from a series with such shocks are approximate.",
        ])
    except ValueError as exc:
        st.warning(f"Decomposition could not be performed: {exc}")

if ctx.bundle.has_country:
    with tabs[5]:
        ui.section("Country breakdown", f"Country-level records for {ctx.filter_note}.")
        var = st.selectbox("Traffic variable", TRAFFIC_COLUMNS, format_func=lambda c: LABELS[c], key="eda_cty_var")
        top = eda.top_countries(ctx.records, var, 15)
        c1, c2 = st.columns([3, 2])
        with c1:
            ui.chart(viz.bar_chart(top["Country"], top["Total"], f"Top 15 Countries – {LABELS[var]}", "Country",
                                   f"Total ({UNITS[var]})", horizontal=True, height=500))
        with c2:
            ui.table(top, height=500, number_format={"Total": "localized", "Share (%)": "%.1f"})
        n = st.slider("Countries in trend chart", 2, 10, 5, key="eda_cty_n")
        leaders = top["Country"].head(n).tolist()
        pivot = (ctx.records[ctx.records["Country"].isin(leaders)].pivot_table(index="Date", columns="Country",
                                                                               values=var, aggfunc="sum"))
        fig = go.Figure()
        palette = ["#2563EB", "#0D9488", "#F59E0B", "#7C3AED", "#DB2777", "#0EA5E9", "#65A30D", "#EA580C", "#475569", "#B91C1C"]
        for i, c in enumerate(leaders):
            if c in pivot:
                fig.add_trace(go.Scatter(x=pivot.index, y=pivot[c], name=c.title(), mode="lines",
                                         line=dict(color=palette[i % 10], width=2),
                                         hovertemplate="%{y:,.0f}<extra>" + c.title() + "</extra>"))
        viz.apply_theme(fig, f"Quarterly {LABELS[var]} – Leading Countries", "Quarter",
                        "Passengers" if var.startswith("Pax") else "Freight (source units)", viz.HEIGHT_MAIN)
        fig.update_yaxes(tickformat="~s")
        ui.chart(fig)
