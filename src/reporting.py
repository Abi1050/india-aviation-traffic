"""Report generation (Markdown, JSON, PDF, ZIP) and static chart export.

Everything here is built from results computed in the current session; nothing
is hard-coded. The module does not import Streamlit so it can be tested directly.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from xml.sax.saxutils import escape

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from config.settings import COLORS, LABELS, MODEL_COLORS, SERIES_COLORS  # noqa: E402
from src.utils import fmt_number, fmt_pct, get_logger, quarter_label  # noqa: E402

log = get_logger(__name__)
TITLE = "Multivariate Time Series Analysis for Forecasting Trends in the Civil Aviation Industry"

REFERENCES = [
    "Vonter (2024–2026). india-aviation-traffic: aviation traffic data for India compiled from DGCA. "
    "https://github.com/Vonter/india-aviation-traffic",
    "Directorate General of Civil Aviation (DGCA), Government of India. Traffic data. https://www.dgca.gov.in",
    "Hyndman, R. J., & Athanasopoulos, G. (2021). Forecasting: Principles and Practice (3rd ed.). OTexts. https://otexts.com/fpp3/",
    "Box, G. E. P., Jenkins, G. M., Reinsel, G. C., & Ljung, G. M. (2015). Time Series Analysis: Forecasting and Control (5th ed.). Wiley.",
    "Dickey, D. A., & Fuller, W. A. (1979). Distribution of the estimators for autoregressive time series with a unit root. "
    "Journal of the American Statistical Association, 74(366), 427–431.",
    "Lütkepohl, H. (2005). New Introduction to Multiple Time Series Analysis. Springer.",
    "Ljung, G. M., & Box, G. E. P. (1978). On a measure of lack of fit in time series models. Biometrika, 65(2), 297–303.",
    "Seabold, S., & Perktold, J. (2010). statsmodels: Econometric and statistical modeling with Python. Proc. 9th Python in Science Conf.",
]

LIMITATIONS = [
    "The series is short (quarterly data from 2015), so parameter estimates, diagnostic tests and interval widths "
    "are uncertain.",
    "The 2020–2021 disruption is a structural break; models fitted across it may misstate seasonality and trend.",
    "Rolling-origin evaluation covers a limited number of one-step forecasts; error metrics have sampling variability.",
    "Prediction intervals assume the model is correct and, for VAR, omit parameter-estimation uncertainty.",
    "Conditional exogenous evaluation uses observed future regressors and overstates real-time accuracy.",
    "Freight units are not documented by the source repository and are reported as given.",
    "Correlations describe association only and do not establish causal relationships.",
]


# --------------------------------------------------------------------------- data assembly
def _records(df: pd.DataFrame | None) -> list[dict]:
    if df is None or len(df) == 0:
        return []
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime("%Y-%m-%d")
    return json.loads(out.to_json(orient="records", default_handler=str))


def build_report_data(*, bundle, quarterly: pd.DataFrame, filter_note: str, target: str, horizon: int, ci: int,
                      period: int, model_settings: dict, stats: pd.DataFrame, adf: pd.DataFrame | None,
                      corr: pd.DataFrame | None, evaluation: dict | None, eval_error: str | None, metric: str,
                      forecast, forecast_model: str | None, forecast_reason: str, forecast_checks: pd.DataFrame | None,
                      forecast_error: str | None, residuals: dict | None, insights: list[str]) -> dict:
    q = quarterly.dropna(how="all")
    data = {
        "title": TITLE,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "dataset": {
            "source": bundle.source, "file": bundle.filename, "format": bundle.fmt,
            "valid_records": int(len(bundle.records)), "excluded_records": int(len(bundle.excluded)),
            "countries": len(bundle.countries) if bundle.has_country else None,
            "start": quarter_label(q.index.min()), "end": quarter_label(q.index.max()), "quarters": int(len(q)),
            "selection": filter_note, "latest_quarter": bundle.latest.get("label"),
            "latest_status": bundle.latest.get("status"),
            "latest_evidence": bundle.latest.get("evidence", []) + bundle.latest.get("concerns", []),
        },
        "settings": {"target": target, "horizon": horizon, "confidence_level": ci, "seasonal_period": period,
                     **model_settings, "ranking_metric": metric},
        "quality": bundle.quality,
        "statistics": stats,
        "adf": adf,
        "correlation": corr,
        "insights": insights,
        "evaluation": None,
        "evaluation_error": eval_error,
        "forecast": None,
        "forecast_error": forecast_error,
        "forecast_checks": forecast_checks,
        "residuals": residuals,
        "limitations": LIMITATIONS,
        "references": REFERENCES,
    }
    if evaluation:
        metrics = evaluation["metrics"]
        best = metrics.loc[metrics[metric].idxmin(), "Model"] if not metrics.empty else None
        data["evaluation"] = {"metrics": metrics, "period": evaluation["period_label"], "n": evaluation["n_common"],
                              "models": evaluation["models"], "best": best, "first_train_size": evaluation["first_train_size"],
                              "forecasts": evaluation["forecasts"].reset_index()}
    if forecast is not None:
        table = forecast.forecast.reset_index()
        table.insert(1, "Period", [quarter_label(d) for d in table["Date"]])
        table["Interval width"] = table["Upper"] - table["Lower"]
        data["forecast"] = {"model": forecast.model, "spec": forecast.spec, "reason": forecast_reason,
                            "table": table, "warnings": forecast.warnings + forecast.notes, "aic": forecast.aic, "bic": forecast.bic,
                            "first": quarter_label(table["Date"].iloc[0]), "last": quarter_label(table["Date"].iloc[-1])}
    return data


def abstract(d: dict) -> str:
    ds = d["dataset"]
    text = (f"This project analyses {ds['quarters']} quarterly observations ({ds['start']} to {ds['end']}) of "
            f"international passenger and freight traffic involving India, with {LABELS[d['settings']['target']]} "
            "as the forecasting target. Exploratory analysis, Augmented Dickey-Fuller tests and seasonal "
            "decomposition characterise trend and seasonality. Seasonal Naive, SARIMAX and VAR models are compared "
            "with expanding-window, one-step-ahead rolling-origin evaluation.")
    ev = d.get("evaluation")
    if ev and ev["best"]:
        m = ev["metrics"].set_index("Model")
        metric = d["settings"]["ranking_metric"]
        text += (f" Over {ev['n']} evaluation quarters ({ev['period']}), {ev['best']} achieved the lowest {metric} "
                 f"({_metric_value(m.loc[ev['best'], metric], metric)})")
        if "Seasonal Naive" in m.index and ev["best"] != "Seasonal Naive":
            base = m.loc["Seasonal Naive", metric]
            gain = (base - m.loc[ev["best"], metric]) / base * 100 if base else np.nan
            text += f", {gain:.1f}% lower than the Seasonal Naive baseline"
        text += "."
    fc = d.get("forecast")
    if fc:
        t = fc["table"]
        text += (f" A {len(t)}-quarter forecast ({fc['first']} to {fc['last']}) from {fc['spec']} ranges from "
                 f"{fmt_number(t['Forecast'].min())} to {fmt_number(t['Forecast'].max())} per quarter, with "
                 f"{d['settings']['confidence_level']}% prediction intervals that widen with the horizon.")
    return text


def _metric_value(v, metric: str) -> str:
    return fmt_pct(v, 2, signed=False) if "%" in metric else fmt_number(v)


# --------------------------------------------------------------------------- markdown / json
def _md_table(df: pd.DataFrame | None, floatfmt: int = 2, max_rows: int = 60) -> str:
    if df is None or len(df) == 0:
        return "_Not available._\n"
    df = df.head(max_rows).copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].dt.strftime("%Y-%m-%d")
        elif pd.api.types.is_float_dtype(df[c]):
            df[c] = [("" if pd.isna(v) else f"{v:,.{floatfmt}f}" if abs(v) < 1e3 else f"{v:,.0f}") for v in df[c]]
    header = "| " + " | ".join(map(str, df.columns)) + " |"
    sep = "| " + " | ".join("---" for _ in df.columns) + " |"
    rows = ["| " + " | ".join(str(v).replace("|", "/") for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join([header, sep, *rows]) + "\n"


def markdown_report(d: dict) -> str:
    ds, s = d["dataset"], d["settings"]
    ev, fc = d.get("evaluation"), d.get("forecast")
    out = [f"# {d['title']}", f"_Report generated {d['generated_at']} from the Civil Aviation Analytics & Forecasting dashboard._", ""]
    out += ["## 1. Project title", d["title"], "", "## 2. Abstract", abstract(d), ""]
    out += ["## 3. Introduction",
            "International air traffic is a key indicator of tourism, trade and connectivity. This project models "
            "quarterly passenger and freight flows between India and other countries to describe historical patterns "
            "and produce short-term passenger forecasts with explicit uncertainty.", ""]
    out += ["## 4. Objectives",
            "- Build a validated quarterly dataset from country-level records.",
            "- Describe trends, seasonality and relationships between passenger and freight series.",
            "- Test stationarity and choose suitable transformations.",
            "- Compare Seasonal Naive, SARIMAX and VAR models with leakage-free rolling-origin evaluation.",
            f"- Forecast {LABELS[s['target']]} for the next {s['horizon']} quarters with prediction intervals.", ""]
    out += ["## 5. Dataset description",
            f"- Source: {ds['source']} (`{ds['file']}`), layout `{ds['format']}`.",
            f"- Coverage: {ds['start']} to {ds['end']} ({ds['quarters']} quarters); selection: {ds['selection']}.",
            f"- Valid records: {ds['valid_records']:,}; excluded records: {ds['excluded_records']:,}"
            + (f"; countries: {ds['countries']}." if ds["countries"] else "."),
            "- Variables: PaxToIndia, PaxFromIndia (passengers), FreightToIndia, FreightFromIndia (freight, source units).",
            f"- Latest quarter {ds['latest_quarter']}: {ds['latest_status']}. " + " ".join(ds["latest_evidence"]), ""]
    out += ["## 6. Data preprocessing",
            "Two-digit years were converted to four digits (00–99 → 2000–2099), quarters validated (1–4), quarter-start "
            "dates created, traffic values checked for non-numeric, missing and negative entries, duplicates checked "
            "per quarter–country key, and records summed once per quarter.", "", _md_table(d["quality"]), ""]
    out += ["## 7. Exploratory data analysis", _md_table(d["statistics"]), ""]
    out += [f"- {line}" for line in d["insights"]] + [""]
    if d.get("correlation") is not None:
        out += ["Correlation matrix (quarterly totals):", "", _md_table(d["correlation"].reset_index().rename(columns={"index": "Variable"}), 3), ""]
    out += ["## 8. Methodology",
            "Data were aggregated to quarterly totals. Stationarity was assessed with ADF tests; seasonality with "
            "classical decomposition and ACF/PACF. Models were evaluated by expanding-window, one-step-ahead "
            "rolling-origin forecasts: at each origin a model is fitted only on earlier quarters, forecasts the next "
            "quarter, and the window then grows by one quarter. All models share the same evaluation quarters.", ""]
    out += ["## 9. Stationarity analysis", _md_table(d.get("adf"), 4),
            "H0 of the ADF test is a unit root; p-values below 0.05 are evidence of stationarity.", ""]
    out += ["## 10. Forecasting models",
            "- **Seasonal Naive** – repeats the value from the same quarter one season earlier (baseline).",
            f"- **SARIMAX** – {s.get('sarimax', '')}; optional exogenous regressors (other traffic series).",
            f"- **VAR** – {s.get('var', '')}; lag order limited by sample size.", ""]
    out += ["## 11. Model evaluation"]
    if ev:
        out += [f"Evaluation quarters: {ev['period']} ({ev['n']} one-step forecasts; first training window "
                f"{ev['first_train_size']} quarters).", "", _md_table(ev["metrics"]),
                f"Best model by {s['ranking_metric']}: **{ev['best']}**.", ""]
    else:
        out += [f"_Evaluation not available: {d.get('evaluation_error')}_", ""]
    out += ["## 12. Forecast results"]
    if fc:
        t = fc["table"].drop(columns=["Date"]).rename(columns={"Lower": f"Lower {s['confidence_level']}%",
                                                               "Upper": f"Upper {s['confidence_level']}%"})
        out += [f"Model: {fc['spec']} ({fc['reason']})", "", _md_table(t)]
        out += [f"- {w}" for w in fc["warnings"]]
        if d.get("forecast_checks") is not None:
            out += ["", "Validation checks:", "", _md_table(d["forecast_checks"])]
        out += ["", "Prediction intervals describe model-based uncertainty and are not guarantees of future traffic.", ""]
    else:
        out += [f"_Forecast not available: {d.get('forecast_error')}_", ""]
    out += ["## 13. Residual diagnostics"]
    r = d.get("residuals")
    if r:
        out += [f"Model: {r.get('model')} – in-sample residuals ({r.get('scale')}).", "",
                _md_table(pd.DataFrame([r["summary"]]), 4)]
        if r.get("ljung_box") is not None:
            out += ["Ljung-Box test:", "", _md_table(r["ljung_box"], 4)]
        if r.get("note"):
            out += [r["note"]]
        out += [""]
    else:
        out += ["_Not available._", ""]
    out += ["## 14. Limitations"] + [f"- {x}" for x in d["limitations"]] + [""]
    out += ["## 15. Conclusion", conclusion(d), ""]
    out += ["## 16. References"] + [f"{i}. {r}" for i, r in enumerate(d["references"], 1)]
    return "\n".join(out) + "\n"


def conclusion(d: dict) -> str:
    ev, fc = d.get("evaluation"), d.get("forecast")
    parts = [f"The validated dataset of {d['dataset']['quarters']} quarters supports quarterly analysis of "
             "international traffic involving India."]
    if ev and ev["best"]:
        parts.append(f"In leakage-free rolling-origin evaluation, {ev['best']} produced the lowest "
                     f"{d['settings']['ranking_metric']} among the compared models; this ranking is specific to the "
                     f"{ev['n']} evaluation quarters and the chosen settings.")
    if fc:
        parts.append(f"The {len(fc['table'])}-quarter forecast should be read together with its prediction intervals, "
                     "which widen materially over the horizon.")
    parts.append("Extending the series and re-evaluating as new quarters are published is recommended.")
    return " ".join(parts)


def json_summary(d: dict) -> str:
    out = {k: v for k, v in d.items() if not isinstance(v, (pd.DataFrame, dict)) or k in ("dataset", "settings")}
    out["quality"] = _records(d["quality"])
    out["statistics"] = _records(d["statistics"])
    out["adf"] = _records(d.get("adf"))
    out["abstract"] = abstract(d)
    if d.get("evaluation"):
        ev = d["evaluation"]
        out["evaluation"] = {"period": ev["period"], "n": ev["n"], "best": ev["best"], "models": ev["models"],
                             "metrics": _records(ev["metrics"])}
    if d.get("forecast"):
        fc = d["forecast"]
        out["forecast"] = {"model": fc["model"], "spec": fc["spec"], "reason": fc["reason"], "warnings": fc["warnings"],
                           "table": _records(fc["table"])}
    out["forecast_checks"] = _records(d.get("forecast_checks"))
    if d.get("residuals"):
        r = d["residuals"]
        out["residuals"] = {"model": r.get("model"), "scale": r.get("scale"), "summary": r["summary"],
                            "ljung_box": _records(r.get("ljung_box"))}
    return json.dumps(out, indent=2, default=lambda o: None if isinstance(o, float) and not np.isfinite(o) else str(o))


# --------------------------------------------------------------------------- static charts (matplotlib)
def _style(ax, title: str, ylabel: str):
    ax.set_title(title, fontsize=13, fontweight="bold", color=COLORS["text"], loc="left")
    ax.set_ylabel(ylabel, color=COLORS["text_secondary"])
    ax.grid(axis="y", color=COLORS["grid"])
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(colors=COLORS["text_secondary"])
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: fmt_number(v, compact=True)))


def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def chart_trends(quarterly: pd.DataFrame, columns: list[str], title: str, ylabel: str) -> bytes:
    fig, ax = plt.subplots(figsize=(9, 3.6))
    for c in columns:
        ax.plot(quarterly.index, quarterly[c], label=LABELS[c], color=SERIES_COLORS[c], lw=2)
    _style(ax, title, ylabel)
    ax.legend(frameon=False)
    return _png(fig)


def chart_forecast(history: pd.Series, forecast: pd.DataFrame, ci: int, title: str, ylabel: str = "Passengers") -> bytes:
    fig, ax = plt.subplots(figsize=(9, 3.8))
    ax.plot(history.index, history.values, color=COLORS["text"], lw=2, label="Observed")
    x = [history.index[-1], *forecast.index]
    ax.fill_between(x, [history.iloc[-1], *forecast["Lower"]], [history.iloc[-1], *forecast["Upper"]],
                    color=COLORS["primary"], alpha=0.15, label=f"{ci}% prediction interval")
    ax.plot(x, [history.iloc[-1], *forecast["Forecast"]], color=COLORS["primary"], lw=2.2, ls="--", marker="o",
            ms=4, label="Point forecast")
    ax.axvline(history.index[-1], color=COLORS["text_muted"], ls=":", lw=1)
    _style(ax, title, ylabel)
    ax.legend(frameon=False, loc="upper left")
    return _png(fig)


def chart_metrics(metrics: pd.DataFrame, metric: str) -> bytes:
    m = metrics.sort_values(metric)
    fig, ax = plt.subplots(figsize=(9, 0.6 * len(m) + 1.4))
    ax.barh(m["Model"], m[metric], color=[MODEL_COLORS.get(x, COLORS["primary"]) for x in m["Model"]])
    ax.invert_yaxis()
    ax.set_title(f"Model Performance by {metric}", fontsize=13, fontweight="bold", color=COLORS["text"], loc="left")
    ax.grid(axis="x", color=COLORS["grid"])
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for i, v in enumerate(m[metric]):
        ax.text(v, i, f"  {_metric_value(v, metric)}", va="center", color=COLORS["text"], fontsize=9)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: fmt_number(v, compact=True)))
    return _png(fig)


def chart_actual_predicted(forecasts: pd.DataFrame, models: list[str]) -> bytes:
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.plot(forecasts.index, forecasts["Actual"], color=COLORS["text"], lw=2.4, marker="o", label="Actual")
    for m in models:
        ax.plot(forecasts.index, forecasts[m], lw=1.8, ls="--", marker="s", ms=3,
                color=MODEL_COLORS.get(m, COLORS["primary"]), label=m)
    _style(ax, "Actual vs Predicted (rolling one-step forecasts)", "Passengers")
    ax.legend(frameon=False, fontsize=8, ncol=2)
    return _png(fig)


def build_charts(d: dict, quarterly: pd.DataFrame, history: pd.Series | None) -> tuple[dict[str, bytes], list[str]]:
    """Render report charts; returns (charts, list of failures) so missing charts are reported, not hidden."""
    charts, failures = {}, []
    jobs = {
        "passenger_trends.png": lambda: chart_trends(quarterly, ["PaxToIndia", "PaxFromIndia"],
                                                     "Passenger Traffic: To vs From India", "Passengers"),
        "freight_trends.png": lambda: chart_trends(quarterly, ["FreightToIndia", "FreightFromIndia"],
                                                   "Freight Traffic: To vs From India", "Freight (source units)"),
    }
    if d.get("evaluation"):
        ev = d["evaluation"]
        jobs["model_performance.png"] = lambda: chart_metrics(ev["metrics"], d["settings"]["ranking_metric"])
        jobs["actual_vs_predicted.png"] = lambda: chart_actual_predicted(ev["forecasts"].set_index("Date"), ev["models"])
    if d.get("forecast") and history is not None:
        fc = d["forecast"]["table"].set_index("Date")
        jobs["future_forecast.png"] = lambda: chart_forecast(history, fc, d["settings"]["confidence_level"],
                                                             f"{LABELS[d['settings']['target']]}: {len(fc)}-Quarter Forecast")
    for name, job in jobs.items():
        try:
            charts[name] = job()
        except Exception as exc:  # noqa: BLE001 - report every chart failure to the user
            log.error("Chart %s failed: %s", name, exc)
            failures.append(f"{name}: {exc}")
    return charts, failures


# --------------------------------------------------------------------------- PDF
def _pdf_text(text: str) -> str:
    replacements = {"≤": "<=", "≥": ">=", "√": "sqrt ", "→": "->", "−": "-", "×": "x", "✅": "", "⚠️": "", "·": "-"}
    for a, b in replacements.items():
        text = str(text).replace(a, b)
    return escape(text)


def _pdf_table(df: pd.DataFrame, max_rows: int = 40, col_widths=None):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    df = df.head(max_rows).copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].dt.strftime("%Y-%m-%d")
    def cell(v):
        if isinstance(v, (float, np.floating)):
            return "" if not np.isfinite(v) else (f"{v:,.3f}" if abs(v) < 100 else f"{v:,.0f}")
        return _pdf_text(str(v))[:60]
    data = [[_pdf_text(str(c)) for c in df.columns]] + [[cell(v) for v in row] for row in df.itertuples(index=False)]
    t = Table(data, repeatRows=1, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B1F33")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F7FB")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DCE5EF")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def pdf_report(d: dict, charts: dict[str, bytes], chart_failures: list[str], forecast_only: bool = False) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.6 * cm,
                            bottomMargin=1.6 * cm, title=d["title"], author="Civil Aviation Analytics dashboard")
    ss = getSampleStyleSheet()
    navy = colors.HexColor("#172B4D")
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=17, leading=21, textColor=navy, alignment=0)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12.5, textColor=colors.HexColor("#2563EB"), spaceBefore=10)
    body = ParagraphStyle("body", parent=ss["BodyText"], fontSize=9.5, leading=13, textColor=navy)
    small = ParagraphStyle("small", parent=body, fontSize=8, textColor=colors.HexColor("#52677F"))
    width = A4[0] - 3.6 * cm

    def img(name):
        if name in charts:
            im = Image(io.BytesIO(charts[name]))
            ratio = im.imageHeight / im.imageWidth
            im.drawWidth, im.drawHeight = width, width * ratio
            return [im, Spacer(1, 6)]
        return [Paragraph(_pdf_text(f"Chart {name} could not be exported."), small)]

    s, ds = d["settings"], d["dataset"]
    story = [Paragraph(_pdf_text(d["title"] + (" – Forecast Report" if forecast_only else "")), h1),
             Paragraph(_pdf_text(f"Generated {d['generated_at']} · {ds['source']} ({ds['file']}) · {ds['selection']}"), small),
             Spacer(1, 8)]
    summary = pd.DataFrame([
        ("Observations", f"{ds['quarters']} quarters ({ds['start']} – {ds['end']})"),
        ("Latest quarter", f"{ds['latest_quarter']} – {ds['latest_status']}"),
        ("Target", LABELS[s["target"]]),
        ("Forecast horizon", f"{s['horizon']} quarters at {s['confidence_level']}% intervals"),
        ("Best evaluated model", (d["evaluation"] or {}).get("best") or "–"),
        ("Forecast model", (d["forecast"] or {}).get("spec") or "–"),
    ], columns=["Item", "Value"])
    story += [Paragraph("Summary", h2), _pdf_table(summary, col_widths=[4.5 * cm, width - 4.5 * cm])]
    if not forecast_only:
        story += [Paragraph("Abstract", h2), Paragraph(_pdf_text(abstract(d)), body)]
        story += [Paragraph("Dataset and preprocessing", h2), _pdf_table(d["quality"][["Check", "Status", "Rows affected", "Action"]])]
        story += [Paragraph("Exploratory analysis", h2)] + img("passenger_trends.png") + img("freight_trends.png")
        story += [Paragraph(_pdf_text(x), body) for x in d["insights"]]
        if d.get("adf") is not None and len(d["adf"]):
            cols = [c for c in ["Variable", "Transform", "ADF statistic", "p-value", "Critical 5%", "Stationary"] if c in d["adf"]]
            story += [Paragraph("Stationarity (ADF)", h2), _pdf_table(d["adf"][cols])]
        story += [PageBreak(), Paragraph("Model evaluation", h2)]
        if d.get("evaluation"):
            ev = d["evaluation"]
            story += [Paragraph(_pdf_text(f"Expanding-window one-step forecasts over {ev['period']} ({ev['n']} quarters). "
                                          f"Best by {s['ranking_metric']}: {ev['best']}."), body)]
            cols = [c for c in ["Model", "N", "MAE", "RMSE", "MAPE (%)", "sMAPE (%)"] if c in ev["metrics"]]
            story += [_pdf_table(ev["metrics"][cols])] + img("model_performance.png") + img("actual_vs_predicted.png")
        else:
            story += [Paragraph(_pdf_text(f"Not available: {d.get('evaluation_error')}"), body)]
    story += [Paragraph("Forecast", h2)]
    if d.get("forecast"):
        fc = d["forecast"]
        story += [Paragraph(_pdf_text(f"{fc['spec']} – {fc['reason']}"), body)] + img("future_forecast.png")
        t = fc["table"].drop(columns=["Date"])
        story += [_pdf_table(t)]
        story += [Paragraph(_pdf_text(w), small) for w in fc["warnings"]]
        if d.get("forecast_checks") is not None:
            story += [Spacer(1, 6), _pdf_table(d["forecast_checks"])]
    else:
        story += [Paragraph(_pdf_text(f"Not available: {d.get('forecast_error')}"), body)]
    if not forecast_only and d.get("residuals"):
        r = d["residuals"]
        story += [Paragraph("Residual diagnostics", h2),
                  Paragraph(_pdf_text(f"{r['model']} in-sample residuals ({r['scale']})."), body),
                  _pdf_table(pd.DataFrame([r["summary"]]))]
        if r.get("note"):
            story += [Paragraph(_pdf_text(r["note"]), small)]
    story += [Paragraph("Interpretation and limitations", h2)]
    story += [Paragraph(_pdf_text("Prediction intervals express model-based uncertainty and are not guarantees."), body)]
    story += [Paragraph(_pdf_text("• " + x), body) for x in d["limitations"]]
    if not forecast_only:
        story += [Paragraph("Conclusion", h2), Paragraph(_pdf_text(conclusion(d)), body),
                  Paragraph("References", h2)] + [Paragraph(_pdf_text(f"{i}. {r}"), small) for i, r in enumerate(d["references"], 1)]
    if chart_failures:
        story += [Paragraph("Chart export issues", h2)] + [Paragraph(_pdf_text(f), small) for f in chart_failures]
    doc.build(story)
    return buf.getvalue()


def build_zip(files: dict[str, bytes | str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            if content is None:
                continue
            zf.writestr(name, content.encode("utf-8") if isinstance(content, str) else content)
    return buf.getvalue()
