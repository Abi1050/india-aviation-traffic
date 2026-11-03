"""Shared Plotly theme and chart builders.

Every builder passes an explicit, non-empty title through ``apply_theme``; that is
what prevents the ``undefined`` titles a figure shows when it is rendered with a
missing title value.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config.settings import COLORS, LABELS, MODEL_COLORS, QUARTER_COLORS, SERIES_COLORS
from src.utils import quarter_labels

FONT = "Inter, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
HEIGHT_MAIN, HEIGHT_SECONDARY, HEIGHT_HEATMAP, HEIGHT_FORECAST = 450, 360, 430, 480


def apply_theme(fig: go.Figure, title: str, x_title: str | None = None, y_title: str | None = None,
                height: int = HEIGHT_SECONDARY, legend: bool = True, subtitle: str | None = None) -> go.Figure:
    if not title or not str(title).strip():
        raise ValueError("Every chart needs a descriptive title.")
    title_cfg = dict(text=f"<b>{title}</b>", x=0.01, xanchor="left", y=0.98, yanchor="top", yref="container",
                     font=dict(size=19, color=COLORS["text"], family=FONT))
    if subtitle:
        title_cfg["subtitle"] = dict(text=subtitle, font=dict(size=12, color=COLORS["text_muted"], family=FONT))
    fig.update_layout(
        title=title_cfg,
        font=dict(family=FONT, size=12, color=COLORS["text_secondary"]),
        paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF", height=height,
        margin=dict(l=64, r=24, t=(104 if subtitle else 88) if legend else (76 if subtitle else 60), b=64),
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0,
                    font=dict(size=12, color=COLORS["text"]), bgcolor="rgba(255,255,255,0)"),
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor=COLORS["border"], font=dict(color=COLORS["text"], size=12)),
        hovermode="x unified",
    )
    axis = dict(showline=True, linecolor=COLORS["border"], ticks="outside", tickcolor=COLORS["border"],
                tickfont=dict(size=12, color=COLORS["text_secondary"]),
                title_font=dict(size=13, color=COLORS["text"]), zeroline=False, automargin=True)
    fig.update_xaxes(**axis, showgrid=False)
    fig.update_yaxes(**axis, showgrid=True, gridcolor=COLORS["grid"])
    if x_title is not None:
        fig.update_xaxes(title_text=x_title)
    if y_title is not None:
        fig.update_yaxes(title_text=y_title)
    return fig


def _label(col: str) -> str:
    return LABELS.get(col, col)


def _y_title(cols: list[str]) -> str:
    if all(c.startswith("Pax") for c in cols):
        return "Passengers"
    if all(c.startswith("Freight") for c in cols):
        return "Freight (source units)"
    return "Traffic (source units)"


# --------------------------------------------------------------------------- general charts
def line_chart(df: pd.DataFrame, columns: list[str], title: str, markers: bool = True, y_title: str | None = None,
               height: int = HEIGHT_MAIN, moving_average: int | None = None, subtitle: str | None = None) -> go.Figure:
    fig = go.Figure()
    for col in columns:
        color = SERIES_COLORS.get(col, COLORS["primary"])
        fig.add_trace(go.Scatter(
            x=df.index, y=df[col], name=_label(col), mode="lines+markers" if markers else "lines",
            line=dict(color=color, width=2.4), marker=dict(size=5),
            customdata=quarter_labels(df.index), hovertemplate="%{customdata}: %{y:,.0f}<extra>" + _label(col) + "</extra>"))
        if moving_average:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[col].rolling(moving_average).mean(), name=f"{_label(col)} – {moving_average}Q average",
                mode="lines", line=dict(color=color, width=1.6, dash="dot"),
                hovertemplate="%{y:,.0f}<extra>" + f"{moving_average}Q avg" + "</extra>"))
    apply_theme(fig, title, "Quarter", y_title or _y_title(columns), height, subtitle=subtitle)
    fig.update_yaxes(tickformat="~s")
    return fig


def bar_chart(x, y, title: str, x_title: str, y_title: str, color: str | list | None = None,
              height: int = HEIGHT_SECONDARY, text_format: str | None = None, horizontal: bool = False,
              hover_format: str = ",.0f") -> go.Figure:
    color = color or COLORS["primary"]
    if horizontal:
        bar = go.Bar(y=x, x=y, orientation="h", marker_color=color,
                     hovertemplate="%{y}: %{x:" + hover_format + "}<extra></extra>")
    else:
        bar = go.Bar(x=x, y=y, marker_color=color, hovertemplate="%{x}: %{y:" + hover_format + "}<extra></extra>")
    if text_format:
        bar.texttemplate = text_format
        bar.textposition = "outside"
        bar.cliponaxis = False
    fig = go.Figure(bar)
    # x_title names the categories and y_title the values, whatever the orientation.
    if horizontal:
        apply_theme(fig, title, y_title, x_title, height, legend=False)
    else:
        apply_theme(fig, title, x_title, y_title, height, legend=False)
    fig.update_layout(hovermode="closest")
    if horizontal:
        fig.update_yaxes(autorange="reversed", showgrid=False)
        fig.update_xaxes(showgrid=True, gridcolor=COLORS["grid"])
    return fig


def growth_chart(growth: pd.Series, title: str, small_base: pd.Series | None = None, height: int = HEIGHT_SECONDARY):
    g = growth.dropna()
    colors = [COLORS["positive"] if v >= 0 else COLORS["negative"] for v in g]
    if small_base is not None:
        colors = [COLORS["warning"] if small_base.get(i, False) else c for i, c in zip(g.index, colors)]
    fig = go.Figure(go.Bar(x=g.index, y=g.values, marker_color=colors, customdata=quarter_labels(g.index),
                           hovertemplate="%{customdata}: %{y:+.1f}%<extra></extra>"))
    apply_theme(fig, title, "Quarter", "Change (%)", height, legend=False,
                subtitle="Amber bars are measured against a very small base and look exaggerated." if small_base is not None and small_base.any() else None)
    fig.update_layout(hovermode="closest")
    fig.add_hline(y=0, line_color=COLORS["text_muted"], line_width=1)
    return fig


def seasonal_comparison_chart(profile: pd.DataFrame, title: str, y_title: str, height: int = HEIGHT_SECONDARY):
    fig = go.Figure()
    for i, q in enumerate(["Q1", "Q2", "Q3", "Q4"]):
        sub = profile[profile["Quarter"] == q]
        fig.add_trace(go.Bar(x=sub["Year"], y=sub["Value"], name=q, marker_color=QUARTER_COLORS[i],
                             hovertemplate="%{x} " + q + ": %{y:,.0f}<extra></extra>"))
    apply_theme(fig, title, "Year", y_title, height)
    fig.update_layout(barmode="group", hovermode="closest")
    fig.update_yaxes(tickformat="~s")
    return fig


def quarter_box_chart(profile: pd.DataFrame, title: str, y_title: str, height: int = HEIGHT_SECONDARY):
    fig = go.Figure()
    for i, q in enumerate(["Q1", "Q2", "Q3", "Q4"]):
        sub = profile[profile["Quarter"] == q]
        fig.add_trace(go.Box(y=sub["Value"], name=q, marker_color=QUARTER_COLORS[i], boxpoints="all",
                             jitter=0.3, customdata=sub["Year"], hovertemplate="%{customdata}: %{y:,.0f}<extra></extra>"))
    apply_theme(fig, title, "Quarter of year", y_title, height, legend=False)
    fig.update_layout(hovermode="closest")
    fig.update_yaxes(tickformat="~s")
    return fig


def heatmap(corr: pd.DataFrame, title: str, height: int = HEIGHT_HEATMAP) -> go.Figure:
    # Two-line labels keep variable names fully visible without rotation.
    labels = [_label(c).replace(" to ", "<br>to ").replace(" from ", "<br>from ") for c in corr.columns]
    fig = go.Figure(go.Heatmap(
        z=corr.values, x=labels, y=labels, zmin=-1, zmax=1,
        colorscale=[[0, "#B91C1C"], [0.5, "#F8FAFC"], [1, "#1D4ED8"]],
        text=np.round(corr.values, 2), texttemplate="%{text:.2f}", textfont=dict(size=14),
        hovertemplate="%{y} vs %{x}: r = %{z:.3f}<extra></extra>",
        colorbar=dict(title=dict(text="r", font=dict(color=COLORS["text"])), tickfont=dict(color=COLORS["text_secondary"]))))
    apply_theme(fig, title, None, None, height, legend=False)
    fig.update_layout(hovermode="closest")
    fig.update_xaxes(showline=False, ticks="", tickangle=0, side="bottom")
    fig.update_yaxes(showline=False, ticks="", showgrid=False, autorange="reversed")
    fig.update_layout(margin=dict(l=110, b=70))
    return fig


def histogram(values, title: str, x_title: str, color: str | None = None, nbins: int | None = None,
              height: int = HEIGHT_SECONDARY):
    fig = go.Figure(go.Histogram(x=values, nbinsx=nbins, marker_color=color or COLORS["primary"],
                                 marker_line=dict(color="#FFFFFF", width=1),
                                 hovertemplate="%{x}: %{y} quarter(s)<extra></extra>"))
    apply_theme(fig, title, x_title, "Frequency", height, legend=False)
    fig.update_layout(hovermode="closest", bargap=0.05)
    return fig


def decomposition_chart(result, title: str, height: int = 640):
    parts = [("Observed", result.observed), ("Trend", result.trend), ("Seasonal", result.seasonal),
             ("Residual", result.resid)]
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                        subplot_titles=[p[0] for p in parts])
    colors = [COLORS["text"], COLORS["primary"], COLORS["positive"], COLORS["warning"]]
    for i, (name, s) in enumerate(parts, start=1):
        mode = "markers" if name == "Residual" else "lines"
        fig.add_trace(go.Scatter(x=s.index, y=s.values, name=name, mode=mode, line=dict(color=colors[i - 1], width=2),
                                 marker=dict(size=6, color=colors[i - 1]),
                                 hovertemplate="%{y:,.3~f}<extra>" + name + "</extra>"), row=i, col=1)
    apply_theme(fig, title, None, None, height, legend=False)
    fig.update_annotations(font=dict(size=13, color=COLORS["text"]))
    fig.update_xaxes(title_text="Quarter", row=4, col=1)
    fig.update_layout(margin=dict(t=80))
    return fig


def correlogram(values: pd.DataFrame, column: str, title: str, height: int = 320):
    lags = values["Lag"].iloc[1:]
    vals = values[column].iloc[1:]
    bound = float(values["Bound"].iloc[0])
    fig = go.Figure()
    for lag, val in zip(lags, vals):
        fig.add_trace(go.Scatter(x=[lag, lag], y=[0, val], mode="lines", line=dict(color=COLORS["primary"], width=2),
                                 showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=lags, y=vals, mode="markers", marker=dict(size=9, color=COLORS["primary"]),
                             name=column, hovertemplate="Lag %{x}: %{y:.3f}<extra></extra>"))
    fig.add_hrect(y0=-bound, y1=bound, fillcolor=COLORS["sky"], opacity=0.15, line_width=0)
    fig.add_hline(y=0, line_color=COLORS["text_muted"], line_width=1)
    apply_theme(fig, title, "Lag (quarters)", column, height, legend=False,
                subtitle="Shaded band: approximate 95% significance bounds (±1.96/√n)")
    fig.update_layout(hovermode="closest")
    fig.update_xaxes(dtick=1)
    return fig


def qq_chart(points: pd.DataFrame, title: str, height: int = HEIGHT_SECONDARY):
    fig = go.Figure([
        go.Scatter(x=points["Theoretical"], y=points["Sample"], mode="markers", name="Residuals",
                   marker=dict(size=8, color=COLORS["primary"]), hovertemplate="%{x:.2f}, %{y:,.3~f}<extra></extra>"),
        go.Scatter(x=points["Theoretical"], y=points["Line"], mode="lines", name="Normal reference",
                   line=dict(color=COLORS["warning"], dash="dash")),
    ])
    apply_theme(fig, title, "Theoretical normal quantiles", "Sample quantiles", height)
    fig.update_layout(hovermode="closest")
    return fig


def residual_series_chart(resid: pd.Series, title: str, y_title: str, height: int = HEIGHT_SECONDARY,
                          color: str | None = None):
    r = resid.dropna()
    fig = go.Figure(go.Scatter(x=r.index, y=r.values, mode="lines+markers", name="Residual",
                               line=dict(color=color or COLORS["primary"], width=2), marker=dict(size=6),
                               customdata=quarter_labels(r.index),
                               hovertemplate="%{customdata}: %{y:,.3~f}<extra></extra>"))
    fig.add_hline(y=0, line_color=COLORS["text_muted"], line_dash="dash")
    apply_theme(fig, title, "Quarter", y_title, height, legend=False)
    return fig


# --------------------------------------------------------------------------- model charts
def forecast_chart(history: pd.Series, forecast: pd.DataFrame, title: str, ci_level: int,
                   fitted: pd.Series | None = None, y_title: str = "Passengers", color: str | None = None,
                   height: int = HEIGHT_FORECAST, subtitle: str | None = None):
    color = color or COLORS["primary"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=history.index, y=history.values, name="Observed", mode="lines+markers",
                             line=dict(color=COLORS["text"], width=2.2), marker=dict(size=4),
                             customdata=quarter_labels(history.index),
                             hovertemplate="%{customdata}: %{y:,.0f}<extra>Observed</extra>"))
    if fitted is not None and fitted.notna().any():
        fig.add_trace(go.Scatter(x=fitted.index, y=fitted.values, name="In-sample fitted", mode="lines",
                                 line=dict(color=COLORS["sky"], width=1.6, dash="dot"),
                                 hovertemplate="%{y:,.0f}<extra>Fitted</extra>"))
    # Connect the forecast to the last observation so the hand-over is visible.
    anchor = pd.DataFrame({"Forecast": [history.iloc[-1]], "Lower": [history.iloc[-1]], "Upper": [history.iloc[-1]]},
                          index=[history.index[-1]])
    band = pd.concat([anchor, forecast[["Forecast", "Lower", "Upper"]]])
    fig.add_trace(go.Scatter(x=band.index, y=band["Upper"], mode="lines", line=dict(width=0), showlegend=False,
                             hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=band.index, y=band["Lower"], mode="lines", line=dict(width=0), fill="tonexty",
                             fillcolor="rgba(37,99,235,0.15)", name=f"{ci_level}% prediction interval",
                             hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=band.index, y=band["Forecast"], name="Point forecast", mode="lines+markers",
                             line=dict(color=color, width=2.6, dash="dash"), marker=dict(size=7),
                             customdata=np.column_stack([quarter_labels(band.index), band["Lower"], band["Upper"]]),
                             hovertemplate="%{customdata[0]}: %{y:,.0f}<br>Interval %{customdata[1]:,.0f} – "
                                           "%{customdata[2]:,.0f}<extra>Forecast</extra>"))
    boundary = history.index[-1] + (forecast.index[0] - history.index[-1]) / 2
    fig.add_vline(x=boundary, line_dash="dot", line_color=COLORS["text_muted"])
    fig.add_annotation(x=boundary, y=1, yref="paper", text="Forecast →", showarrow=False, xanchor="left",
                       font=dict(color=COLORS["text_secondary"], size=12))
    apply_theme(fig, title, "Quarter", y_title, height, subtitle=subtitle)
    fig.update_yaxes(tickformat="~s")
    return fig


def actual_vs_predicted(forecasts: pd.DataFrame, models: list[str], title: str, height: int = HEIGHT_MAIN,
                        history: pd.Series | None = None, y_title: str = "Passengers"):
    fig = go.Figure()
    if history is not None:
        fig.add_trace(go.Scatter(x=history.index, y=history.values, name="History", mode="lines",
                                 line=dict(color="#94A3B8", width=1.6), hovertemplate="%{y:,.0f}<extra>History</extra>"))
    fig.add_trace(go.Scatter(x=forecasts.index, y=forecasts["Actual"], name="Actual", mode="lines+markers",
                             line=dict(color=COLORS["text"], width=2.6), marker=dict(size=7),
                             hovertemplate="%{y:,.0f}<extra>Actual</extra>"))
    dashes = ["dash", "dot", "dashdot", "longdash", "longdashdot"]
    for i, m in enumerate(models):
        fig.add_trace(go.Scatter(x=forecasts.index, y=forecasts[m], name=m, mode="lines+markers",
                                 line=dict(color=MODEL_COLORS.get(m, COLORS["primary"]), width=2, dash=dashes[i % 5]),
                                 marker=dict(size=6), hovertemplate="%{y:,.0f}<extra>" + m + "</extra>"))
    apply_theme(fig, title, "Quarter", y_title, height)
    fig.update_yaxes(tickformat="~s")
    return fig


def metric_bars(metrics: pd.DataFrame, metric: str, title: str, height: int = 330):
    m = metrics.dropna(subset=[metric]).sort_values(metric)
    colors = [MODEL_COLORS.get(x, COLORS["primary"]) for x in m["Model"]]
    is_pct = "%" in metric
    fig = bar_chart(m["Model"], m[metric], title, None, metric, color=colors, height=height,
                    text_format="%{x:.2f}%" if is_pct else "%{x:,.3~s}", horizontal=True,
                    hover_format=".2f" if is_pct else ",.0f")
    fig.update_layout(margin=dict(l=200, r=60))
    return fig


def error_bars(errors: pd.DataFrame, title: str, height: int = HEIGHT_SECONDARY):
    fig = go.Figure()
    for m in errors["Model"].unique():
        sub = errors[errors["Model"] == m]
        fig.add_trace(go.Bar(x=sub["Date"], y=sub["Error"], name=m, marker_color=MODEL_COLORS.get(m, COLORS["primary"]),
                             hovertemplate="%{y:,.0f}<extra>" + m + "</extra>"))
    fig.add_hline(y=0, line_color=COLORS["text_muted"], line_width=1)
    apply_theme(fig, title, "Quarter", "Actual − predicted", height,
                subtitle="Positive = model under-predicted; negative = over-predicted")
    fig.update_layout(barmode="group")
    fig.update_yaxes(tickformat="~s")
    return fig


def error_distribution(errors: pd.DataFrame, title: str, height: int = HEIGHT_SECONDARY):
    fig = go.Figure()
    for m in errors["Model"].unique():
        sub = errors[errors["Model"] == m]
        fig.add_trace(go.Box(y=sub["Error"], name=m, marker_color=MODEL_COLORS.get(m, COLORS["primary"]),
                             boxpoints="all", jitter=0.3, customdata=quarter_labels(sub["Date"]),
                             hovertemplate="%{customdata}: %{y:,.0f}<extra>" + m + "</extra>"))
    fig.add_hline(y=0, line_color=COLORS["text_muted"], line_width=1)
    apply_theme(fig, title, None, "Actual − predicted", height, legend=False)
    fig.update_layout(hovermode="closest")
    fig.update_yaxes(tickformat="~s")
    return fig
