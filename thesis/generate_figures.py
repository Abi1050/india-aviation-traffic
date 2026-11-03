"""Generate every thesis figure and the numeric results used in the thesis text.

Run from the project root:
    python thesis/generate_figures.py

Outputs:
    thesis/figures/Figure_XX_<name>.png   (numbered as in the thesis)
    thesis/results.json                   (all numbers quoted in the thesis)
All values are computed from aggregated/international/country.csv with the same
code the Streamlit dashboard uses (src/).
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402
from scipy import stats  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from config.settings import COLORS, LABELS, MODEL_COLORS, QUARTER_COLORS, SERIES_COLORS, TRAFFIC_COLUMNS  # noqa: E402
from src import data_loader, diagnostics as dg, eda, evaluation as ev, forecasting as fc  # noqa: E402
from src.utils import quarter_label  # noqa: E402

FIG = ROOT / "thesis" / "figures"
FIG.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
                     "axes.edgecolor": "#9AA9BA", "axes.grid": True, "grid.color": "#E8EEF5", "axes.axisbelow": True,
                     "figure.dpi": 100, "savefig.dpi": 200, "savefig.bbox": "tight"})
MILLION = matplotlib.ticker.FuncFormatter(lambda v, _: f"{v / 1e6:.0f}M" if abs(v) >= 1e6 else f"{v / 1e3:.0f}K")
FIGURES: list[tuple[int, str, str]] = []
R: dict = {}


def save(fig, number: int, slug: str, title: str) -> None:
    # Thesis figures are numbered in document order: the schedule Gantt chart (Chapter 5)
    # precedes the analysis outputs (Chapter 6), so it becomes Figure 4 and 4-36 shift by one.
    number = 4 if number == 37 else number + 1 if 4 <= number <= 36 else number
    path = FIG / f"Figure_{number:02d}_{slug}.png"
    fig.savefig(path)
    plt.close(fig)
    FIGURES.append((number, path.name, title))


def table(df: pd.DataFrame) -> list[dict]:
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[c]):
            out[c] = out[c].dt.strftime("%Y-%m-%d")
    return json.loads(out.to_json(orient="records"))


# =========================================================================== data
bundle = data_loader.load_country_source()
q = bundle.quarterly
rec = bundle.records
pax = q["PaxToIndia"]
R["dataset"] = {
    "raw_rows": len(bundle.raw), "valid_records": len(rec), "excluded": len(bundle.excluded),
    "countries_raw": int(bundle.raw["Country"].nunique()), "countries": len(bundle.countries),
    "quarters": len(q), "start": quarter_label(q.index.min()), "end": quarter_label(q.index.max()),
    "latest": bundle.latest["label"], "latest_status": bundle.latest["status"],
    "latest_evidence": bundle.latest["evidence"],
}
R["quality"] = table(bundle.quality)
R["head"] = table(bundle.raw.head(5))
R["quarterly_head"] = table(q.head(4).reset_index())
R["quarterly_tail"] = table(q.tail(4).reset_index())
R["records_per_quarter"] = {"min": int(rec.groupby("Date").size().min()), "max": int(rec.groupby("Date").size().max())}

# =========================================================================== methodology diagrams
def box(ax, x, y, w, h, text, color, fc="#FFFFFF", size=9):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08", ec=color, fc=fc, lw=1.6))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=size, color=COLORS["text"], wrap=True)


def arrow(ax, x1, y1, x2, y2):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="-|>", color="#52677F", lw=1.4))


fig, ax = plt.subplots(figsize=(11, 6.2))
ax.set_xlim(0, 11); ax.set_ylim(0.85, 6.2); ax.axis("off")
layers = [
    (5.1, "Data layer", "#2563EB", ["country.csv\n(DGCA via GitHub)", "Quarterly aggregate\n(notebook output)", "Uploaded CSV", "Remote refresh\n(on request)"]),
    (3.75, "Processing layer", "#0D9488", ["Schema detection\n& validation", "Cleaning &\nquarterly aggregation", "Filters (date,\ncountry)", "Data-quality\nreport"]),
    (2.4, "Analytics layer", "#F59E0B", ["EDA & statistics", "ADF, ACF/PACF,\ndecomposition", "Seasonal Naive,\nSARIMAX, VAR", "Rolling-origin\nevaluation"]),
    (1.05, "Presentation layer", "#7C3AED", ["Streamlit pages\n(10)", "Plotly charts", "Reports: PDF,\nMarkdown, JSON", "ZIP export"]),
]
for y, name, color, items in layers:
    ax.text(0.1, y + 0.45, name, fontsize=10.5, fontweight="bold", color=color, va="center")
    for i, item in enumerate(items):
        box(ax, 2.2 + i * 2.2, y, 1.95, 0.9, item, color)
    if y > 1.2:
        arrow(ax, 6.5, y - 0.02, 6.5, y - 0.43)
ax.set_title("System architecture of the Civil Aviation Analytics & Forecasting platform", loc="left")
save(fig, 1, "System_Architecture", "System architecture of the analytics and forecasting platform")

fig, ax = plt.subplots(figsize=(11, 3.4))
ax.set_xlim(0, 11); ax.set_ylim(0, 3.4); ax.axis("off")
steps = ["1. Data\ncollection", "2. Validation\n& cleaning", "3. Quarterly\naggregation", "4. Exploratory\nanalysis",
         "5. Stationarity &\nseasonality tests", "6. Model\nspecification", "7. Rolling-origin\nevaluation",
         "8. Future forecast\n& intervals", "9. Diagnostics\n& reporting"]
cols = ["#2563EB", "#2563EB", "#2563EB", "#0D9488", "#0D9488", "#F59E0B", "#F59E0B", "#7C3AED", "#7C3AED"]
for i, (s, c) in enumerate(zip(steps, cols)):
    x = 0.15 + (i % 5) * 2.15
    y = 2.0 if i < 5 else 0.4
    box(ax, x, y, 1.85, 0.95, s, c, size=8.8)
    if i % 5 != 4 and i < 8:
        arrow(ax, x + 1.86, y + 0.47, x + 2.13, y + 0.47)
arrow(ax, 0.15 + 4 * 2.15 + 0.92, 1.98, 0.15 + 0.92, 1.37)
ax.set_title("Methodology workflow", loc="left")
save(fig, 2, "Methodology_Workflow", "Methodology workflow followed in the project")

fig, ax = plt.subplots(figsize=(11, 3.6))
n_show, test = 46, 12
for k in range(5):
    origin = n_show - test + k
    y = 4 - k
    ax.barh(y, origin, left=0, color="#BFD3F6", edgecolor="#2563EB", height=0.55)
    ax.barh(y, 1, left=origin, color=COLORS["warning"], height=0.55)
    ax.text(origin + 1.4, y, f"origin {k + 1}: train {origin} quarters → forecast {quarter_label(q.index[origin])}",
            va="center", fontsize=8.5)
ax.text(1, -0.9, "… repeated for all 12 evaluation quarters (2023 Q3 – 2026 Q2)", fontsize=9, color="#52677F")
ax.set_yticks([]); ax.set_xlim(0, 62); ax.set_ylim(-1.3, 4.6); ax.set_xlabel("Quarter index (1 = 2015 Q1)")
ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, fc="#BFD3F6", ec="#2563EB"), plt.Rectangle((0, 0), 1, 1, fc=COLORS["warning"])],
          labels=["Training window (expanding)", "One-step forecast quarter"], loc="lower right", fontsize=8.5)
ax.set_title("Expanding-window rolling-origin evaluation", loc="left")
save(fig, 3, "Rolling_Origin_Scheme", "Expanding-window rolling-origin evaluation scheme")

# =========================================================================== EDA
def line(ax, cols, title, ylabel="Passengers"):
    for c in cols:
        ax.plot(q.index, q[c], color=SERIES_COLORS[c], lw=2, marker="o", ms=2.5, label=LABELS[c])
    ax.set_title(title, loc="left"); ax.set_ylabel(ylabel); ax.yaxis.set_major_formatter(MILLION); ax.legend(frameon=False)


fig, ax = plt.subplots(figsize=(10, 4.2)); line(ax, ["PaxToIndia", "PaxFromIndia"], "Quarterly international passenger traffic")
ax.axvspan(pd.Timestamp("2020-01-01"), pd.Timestamp("2021-12-31"), color="#FEE2E2", alpha=0.5, lw=0)
ax.text(pd.Timestamp("2020-02-01"), q["PaxToIndia"].max() * 1.02, "COVID-19 period", fontsize=8, color="#991B1B")
save(fig, 4, "Passenger_Traffic_Trends", "Quarterly passenger traffic to and from India, 2015 Q1 – 2026 Q2")

fig, ax = plt.subplots(figsize=(10, 4.2)); line(ax, ["FreightToIndia", "FreightFromIndia"], "Quarterly international freight traffic", "Freight (source units)")
save(fig, 5, "Freight_Traffic_Trends", "Quarterly freight traffic to and from India, 2015 Q1 – 2026 Q2")

fig, ax = plt.subplots(figsize=(10, 4))
ax.plot(q.index, pax, color=SERIES_COLORS["PaxToIndia"], lw=2, marker="o", ms=3, label="Passengers to India")
ax.plot(q.index, pax.rolling(4).mean(), color="#0B1F33", lw=2, ls="--", label="4-quarter moving average")
ax.set_title("Passengers to India with 4-quarter moving average", loc="left"); ax.yaxis.set_major_formatter(MILLION)
ax.set_ylabel("Passengers"); ax.legend(frameon=False)
save(fig, 6, "PaxToIndia_Moving_Average", "Passengers to India with a four-quarter moving average")

g = eda.growth_table(pax)
R["growth"] = {
    "qoq_min": float(g["QoQ change (%)"].min()), "qoq_min_q": quarter_label(g["QoQ change (%)"].idxmin()),
    "qoq_max": float(g["QoQ change (%)"].max()), "qoq_max_q": quarter_label(g["QoQ change (%)"].idxmax()),
    "yoy_min": float(g["YoY change (%)"].min()), "yoy_min_q": quarter_label(g["YoY change (%)"].idxmin()),
    "yoy_max": float(g["YoY change (%)"].max()), "yoy_max_q": quarter_label(g["YoY change (%)"].idxmax()),
    "yoy_latest": float(g["YoY change (%)"].iloc[-1]), "small_base_quarters": [quarter_label(i) for i in g.index[g["Small base"]]],
}
for num, col, title in ((7, "QoQ change (%)", "Quarter-over-quarter change"), (8, "YoY change (%)", "Year-over-year change")):
    s = g[col].dropna()
    colors = [COLORS["warning"] if g.loc[i, "Small base"] else (COLORS["positive"] if v >= 0 else COLORS["negative"]) for i, v in s.items()]
    fig, ax = plt.subplots(figsize=(10, 3.8))
    ax.bar(s.index, s.values, width=70, color=colors)
    ax.axhline(0, color="#52677F", lw=0.8)
    ax.set_title(f"{title} in passengers to India (%)", loc="left"); ax.set_ylabel("Change (%)")
    ax.text(0.01, 0.95, "Amber: measured from a very small base (2020–2021)", transform=ax.transAxes, fontsize=8, color="#92400E", va="top")
    save(fig, num, f"PaxToIndia_{'QoQ' if 'QoQ' in col else 'YoY'}_Growth", f"{title} in passengers to India")

annual = eda.annual_summary(q, TRAFFIC_COLUMNS)
R["annual"] = table(annual)
for num, cols, label, ylabel in ((9, ["PaxToIndia", "PaxFromIndia"], "Passenger", "Passengers"),
                                 (10, ["FreightToIndia", "FreightFromIndia"], "Freight", "Freight (source units)")):
    fig, ax = plt.subplots(figsize=(10, 3.9))
    x = np.arange(len(annual)); w = 0.4
    for i, c in enumerate(cols):
        ax.bar(x + (i - 0.5) * w, annual[c], w, color=SERIES_COLORS[c], label=LABELS[c])
    ax.set_xticks(x, [f"{y}{'*' if not c else ''}" for y, c in zip(annual["Year"], annual["Complete year"])])
    ax.yaxis.set_major_formatter(MILLION); ax.set_ylabel(ylabel); ax.legend(frameon=False)
    ax.set_title(f"Annual {label.lower()} traffic (* = partial year)", loc="left")
    save(fig, num, f"Annual_{label}_Traffic", f"Annual {label.lower()} traffic totals")

prof = eda.seasonal_profile(q, "PaxToIndia")
fig, ax = plt.subplots(figsize=(10, 4))
years = sorted(prof["Year"].unique()); x = np.arange(len(years)); w = 0.2
for i, qq in enumerate(["Q1", "Q2", "Q3", "Q4"]):
    sub = prof[prof["Quarter"] == qq].set_index("Year").reindex(years)
    ax.bar(x + (i - 1.5) * w, sub["Value"], w, color=QUARTER_COLORS[i], label=qq)
ax.set_xticks(x, years); ax.yaxis.set_major_formatter(MILLION); ax.legend(frameon=False, ncol=4)
ax.set_title("Passengers to India by quarter of year", loc="left"); ax.set_ylabel("Passengers")
save(fig, 11, "Quarterly_Seasonal_Comparison", "Passengers to India by quarter and year")

fig, ax = plt.subplots(figsize=(8, 4))
data = [prof[prof["Quarter"] == qq]["Value"].values for qq in ["Q1", "Q2", "Q3", "Q4"]]
bp = ax.boxplot(data, patch_artist=True, tick_labels=["Q1", "Q2", "Q3", "Q4"], widths=0.55)
for patch, c in zip(bp["boxes"], QUARTER_COLORS):
    patch.set_facecolor(c); patch.set_alpha(0.35); patch.set_edgecolor(c)
for i, d in enumerate(data):
    ax.scatter(np.random.default_rng(i).normal(i + 1, 0.05, len(d)), d, s=14, color=QUARTER_COLORS[i], zorder=3)
ax.yaxis.set_major_formatter(MILLION); ax.set_title("Distribution of passengers to India by quarter of year", loc="left")
ax.set_ylabel("Passengers")
save(fig, 12, "Quarter_of_Year_Boxplot", "Distribution of passengers to India by quarter of year")
R["quarter_means"] = {qq: float(np.mean(d)) for qq, d in zip(["Q1", "Q2", "Q3", "Q4"], data)}
pre = pax[pax.index < "2020-01-01"]; post = pax[pax.index >= "2022-01-01"]
R["quarter_means_pre"] = {f"Q{k}": float(pre[pre.index.quarter == k].mean()) for k in range(1, 5)}
R["quarter_means_post"] = {f"Q{k}": float(post[post.index.quarter == k].mean()) for k in range(1, 5)}

fig, axes = plt.subplots(2, 2, figsize=(10, 6.2))
for ax, c in zip(axes.flat, TRAFFIC_COLUMNS):
    ax.hist(q[c], bins=12, color=SERIES_COLORS[c], edgecolor="white")
    ax.set_title(LABELS[c], loc="left", fontsize=10.5); ax.xaxis.set_major_formatter(MILLION); ax.set_ylabel("Quarters")
fig.suptitle("Distribution of quarterly values", x=0.06, ha="left", fontweight="bold")
fig.tight_layout()
save(fig, 13, "Variable_Distributions", "Histograms of the four quarterly traffic variables")

stats_df = eda.descriptive_statistics(q, TRAFFIC_COLUMNS)
R["descriptive"] = table(stats_df)

corr = eda.correlation_matrix(q, TRAFFIC_COLUMNS)
logchg = np.log(q[TRAFFIC_COLUMNS]).diff().dropna()
corr_chg = eda.correlation_matrix(logchg, TRAFFIC_COLUMNS)
corr_sp = eda.correlation_matrix(q, TRAFFIC_COLUMNS, "spearman")
R["corr_levels"] = corr.round(4).to_dict()
R["corr_changes"] = corr_chg.round(4).to_dict()
R["corr_spearman"] = corr_sp.round(4).to_dict()
short = ["Pax to India", "Pax from India", "Freight to India", "Freight from India"]
for num, m, title in ((14, corr, "levels"), (15, corr_chg, "quarter-over-quarter log changes")):
    fig, ax = plt.subplots(figsize=(6.6, 5.4))
    im = ax.imshow(m.values, cmap="RdBu", vmin=-1, vmax=1)
    ax.set_xticks(range(4), short, rotation=20); ax.set_yticks(range(4), short); ax.grid(False)
    for i in range(4):
        for j in range(4):
            ax.text(j, i, f"{m.values[i, j]:.2f}", ha="center", va="center", color="white" if abs(m.values[i, j]) > 0.6 else COLORS["text"])
    fig.colorbar(im, ax=ax, fraction=0.046, label="Pearson r")
    ax.set_title(f"Correlation matrix – {title}", loc="left")
    save(fig, num, f"Correlation_Heatmap_{'Levels' if num == 14 else 'Log_Changes'}", f"Pearson correlation matrix of the traffic variables ({title})")

fig, axes = plt.subplots(4, 4, figsize=(10, 10))
for i, a in enumerate(TRAFFIC_COLUMNS):
    for j, b in enumerate(TRAFFIC_COLUMNS):
        ax = axes[i, j]
        if i == j:
            ax.hist(q[a], bins=10, color=SERIES_COLORS[a], edgecolor="white")
        else:
            ax.scatter(q[b], q[a], s=10, color=SERIES_COLORS[a], alpha=0.8)
        ax.tick_params(labelsize=6)
        ax.xaxis.set_major_formatter(MILLION); ax.yaxis.set_major_formatter(MILLION)
        if i == 3: ax.set_xlabel(short[j], fontsize=8)
        if j == 0: ax.set_ylabel(short[i], fontsize=8)
fig.suptitle("Pairwise relationships between the traffic variables", x=0.06, ha="left", fontweight="bold")
fig.tight_layout()
save(fig, 16, "Scatter_Matrix", "Scatter-plot matrix of the four quarterly traffic variables")

top = eda.top_countries(rec, "PaxToIndia", 15)
R["top_countries"] = table(top)
R["top5_share"] = float(top["Share (%)"].head(5).sum())
fig, ax = plt.subplots(figsize=(10, 5.4))
ax.barh(top["Country"].str.title()[::-1], top["Total"][::-1], color=SERIES_COLORS["PaxToIndia"])
for i, (t, s) in enumerate(zip(top["Total"][::-1], top["Share (%)"][::-1])):
    ax.text(t, i, f"  {s:.1f}%", va="center", fontsize=8)
ax.xaxis.set_major_formatter(MILLION); ax.set_title("Top 15 origin countries – passengers to India (2015–2026)", loc="left")
ax.set_xlabel("Total passengers")
save(fig, 17, "Top_Countries", "Top 15 countries by total passengers to India")

leaders = top["Country"].head(5).tolist()
pv = rec[rec["Country"].isin(leaders)].pivot_table(index="Date", columns="Country", values="PaxToIndia", aggfunc="sum")
share = pv.div(q["PaxToIndia"], axis=0) * 100
fig, ax = plt.subplots(figsize=(10, 4))
for i, c in enumerate(leaders):
    ax.plot(share.index, share[c], lw=2, label=c.title(), color=["#2563EB", "#0D9488", "#F59E0B", "#7C3AED", "#DB2777"][i])
ax.set_ylabel("Share of passengers to India (%)"); ax.legend(frameon=False, ncol=5, fontsize=8)
ax.set_title("Quarterly share of the five largest origin countries", loc="left")
save(fig, 18, "Top_Country_Shares", "Quarterly share of passengers to India for the five largest origin countries")
R["share_latest"] = {c: float(share[c].iloc[-1]) for c in leaders}
R["share_first"] = {c: float(share[c].iloc[0]) for c in leaders}

# =========================================================================== decomposition & diagnostics
dec_info = {}
for num, col in ((19, "PaxToIndia"), (20, "FreightToIndia")):
    res = eda.decompose(q[col], 4, "additive")
    fig, axes = plt.subplots(4, 1, figsize=(10, 8), sharex=True)
    for ax, (name, s, c) in zip(axes, [("Observed", res.observed, COLORS["text"]), ("Trend", res.trend, COLORS["primary"]),
                                       ("Seasonal", res.seasonal, COLORS["positive"]), ("Residual", res.resid, COLORS["warning"])]):
        if name == "Residual":
            ax.scatter(s.index, s.values, s=14, color=c); ax.axhline(0, color="#52677F", lw=0.8)
        else:
            ax.plot(s.index, s.values, color=c, lw=2)
        ax.set_ylabel(name); ax.yaxis.set_major_formatter(MILLION)
    axes[0].set_title(f"Additive seasonal decomposition – {LABELS[col]} (period 4)", loc="left")
    fig.tight_layout()
    save(fig, num, f"Seasonal_Decomposition_{col}", f"Additive seasonal decomposition of {LABELS[col].lower()}")
    resid = res.resid.dropna()
    dec_info[col] = {
        "seasonal_strength": float(max(0, 1 - resid.var() / (res.seasonal.loc[resid.index] + resid).var())),
        "trend_strength": float(max(0, 1 - resid.var() / (res.trend.loc[resid.index] + resid).var())),
        "indices": {f"Q{k}": float(v) for k, v in res.seasonal.groupby(res.seasonal.index.quarter).first().items()},
    }
R["decomposition"] = dec_info

adf = dg.adf_table(q, TRAFFIC_COLUMNS, dg.TRANSFORMS, 0.05, 4)
R["adf"] = table(adf.drop(columns=["Conclusion"]))
adf_ct = dg.adf_table(q, TRAFFIC_COLUMNS, ["Level"], 0.05, 4, "ct")
R["adf_ct"] = table(adf_ct[["Variable", "ADF statistic", "p-value", "Stationary"]])

acf_info = {}
for num, tr in ((21, "Level"), (22, "First difference")):
    vals = dg.acf_pacf(dg.transform_series(pax, tr), 12)
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
    for ax, col in zip(axes, ["ACF", "PACF"]):
        lags, v = vals["Lag"][1:], vals[col][1:]
        ax.vlines(lags, 0, v, color=COLORS["primary"], lw=2); ax.scatter(lags, v, color=COLORS["primary"], s=18, zorder=3)
        b = vals["Bound"].iloc[0]; ax.axhspan(-b, b, color=COLORS["sky"], alpha=0.18); ax.axhline(0, color="#52677F", lw=0.8)
        ax.set_title(f"{col} – passengers to India ({tr.lower()})", loc="left", fontsize=10.5); ax.set_xlabel("Lag (quarters)")
        ax.set_xticks(range(1, 13))
    fig.tight_layout()
    save(fig, num, f"ACF_PACF_{tr.replace(' ', '_')}", f"ACF and PACF of passengers to India ({tr.lower()})")
    acf_info[tr] = {"bound": float(vals["Bound"].iloc[0]),
                    "acf_sig": [int(l) for l, a in zip(vals["Lag"][1:], vals["ACF"][1:]) if abs(a) > vals["Bound"].iloc[0]],
                    "pacf_sig": [int(l) for l, a in zip(vals["Lag"][1:], vals["PACF"][1:]) if abs(a) > vals["Bound"].iloc[0]],
                    "acf": [round(float(a), 3) for a in vals["ACF"][1:7]], "pacf": [round(float(a), 3) for a in vals["PACF"][1:7]]}
R["acf"] = acf_info

fig, ax = plt.subplots(figsize=(10, 3.9))
for k in range(1, 5):
    s = pax[pax.index.quarter == k]
    ax.plot(s.index.year, s.values, marker="o", lw=2, color=QUARTER_COLORS[k - 1], label=f"Q{k}")
ax.yaxis.set_major_formatter(MILLION); ax.legend(frameon=False, ncol=4); ax.set_ylabel("Passengers")
ax.set_title("Seasonal sub-series – passengers to India", loc="left")
save(fig, 23, "Seasonal_Subseries", "Seasonal sub-series plot of passengers to India")

# =========================================================================== models
scfg, vcfg = fc.SarimaxConfig(), fc.VarConfig()
models = [fc.NAIVE, fc.SARIMAX, fc.VAR_MODEL, fc.EXOG_CONDITIONAL, fc.EXOG_OPERATIONAL]
roll = ev.rolling_origin(q, "PaxToIndia", models, 12, 4, scfg, vcfg)
f = roll["forecasts"]
R["rolling_metrics"] = table(roll["metrics"])
R["rolling_period"] = roll["period_label"]
R["rolling_forecasts"] = table(f.reset_index())
R["rolling_first_train"] = roll["first_train_size"]

full = fc.sarimax_forecast(pax, 8, scfg, 95)
fig, ax = plt.subplots(figsize=(10, 4))
ax.plot(pax.index, pax, color=COLORS["text"], lw=2, marker="o", ms=3, label="Actual")
ax.plot(full.fitted.index, full.fitted, color=COLORS["sky"], lw=2, ls="--", label="SARIMAX in-sample fitted")
ax.yaxis.set_major_formatter(MILLION); ax.legend(frameon=False); ax.set_ylabel("Passengers")
ax.set_title("SARIMAX(1,1,1)(1,1,0,4): actual vs in-sample fitted values", loc="left")
save(fig, 24, "SARIMAX_Fitted_vs_Actual", "SARIMAX(1,1,1)(1,1,0,4) actual versus in-sample fitted values")
R["sarimax_fit"] = {"aic": full.aic, "bic": full.bic, "converged": full.converged, "params": full.params, "n": full.n_obs}

fig, ax = plt.subplots(figsize=(10, 4.3))
hist = pax.loc[:f.index.min()].iloc[-9:]
ax.plot(hist.index, hist, color="#94A3B8", lw=1.6, label="History")
ax.plot(f.index, f["Actual"], color=COLORS["text"], lw=2.6, marker="o", label="Actual")
for m, ls in ((fc.NAIVE, "--"), (fc.SARIMAX, ":"), (fc.VAR_MODEL, "-.")):
    ax.plot(f.index, f[m], color=MODEL_COLORS[m], lw=2, ls=ls, marker="s", ms=4, label=m)
ax.yaxis.set_major_formatter(MILLION); ax.legend(frameon=False, ncol=4, fontsize=8.5); ax.set_ylabel("Passengers")
ax.set_title("Rolling one-step forecasts vs actual (2023 Q3 – 2026 Q2)", loc="left")
save(fig, 25, "Rolling_Actual_vs_Predicted", "Rolling-origin one-step forecasts of Seasonal Naive, SARIMAX and VAR against actual values")

fig, ax = plt.subplots(figsize=(10, 4.1))
ax.plot(f.index, f["Actual"], color=COLORS["text"], lw=2.6, marker="o", label="Actual")
for m, ls in ((fc.SARIMAX, ":"), (fc.EXOG_CONDITIONAL, "--"), (fc.EXOG_OPERATIONAL, "-.")):
    ax.plot(f.index, f[m], color=MODEL_COLORS[m], lw=2, ls=ls, marker="s", ms=4, label=m)
ax.yaxis.set_major_formatter(MILLION); ax.legend(frameon=False, fontsize=8.5); ax.set_ylabel("Passengers")
ax.set_title("Effect of exogenous-variable information on rolling forecasts", loc="left")
save(fig, 26, "Exogenous_Conditional_vs_Operational", "Conditional versus operational SARIMAX with exogenous regressors")

met = roll["metrics"].set_index("Model")
fig, axes = plt.subplots(1, 3, figsize=(12, 3.8))
for ax, col in zip(axes, ["MAE", "RMSE", "MAPE (%)"]):
    s = met[col].sort_values()
    ax.barh([m.replace(" + exog ", "\n+ exog ") for m in s.index], s.values, color=[MODEL_COLORS[m] for m in s.index])
    ax.invert_yaxis(); ax.set_title(col, loc="left")
    for i, v in enumerate(s.values):
        ax.text(v, i, f" {v:.2f}" if "%" in col else f" {v / 1e3:.0f}K", va="center", fontsize=8)
    if "%" not in col: ax.xaxis.set_major_formatter(MILLION)
    ax.tick_params(axis="y", labelsize=7.5)
fig.suptitle("Rolling-origin error metrics (12 one-step forecasts)", x=0.02, ha="left", fontweight="bold")
fig.tight_layout()
save(fig, 27, "Model_Error_Metrics", "MAE, RMSE and MAPE of the five model variants")

err = roll["errors"]
fig, ax = plt.subplots(figsize=(10, 4))
x = np.arange(12); w = 0.27
for i, m in enumerate([fc.NAIVE, fc.SARIMAX, fc.VAR_MODEL]):
    sub = err[err["Model"] == m]
    ax.bar(x + (i - 1) * w, sub["Error"], w, color=MODEL_COLORS[m], label=m)
ax.axhline(0, color="#52677F", lw=0.8); ax.set_xticks(x, [quarter_label(d) for d in f.index], rotation=45, fontsize=8)
ax.yaxis.set_major_formatter(MILLION); ax.set_ylabel("Actual − predicted"); ax.legend(frameon=False, ncol=3)
ax.set_title("Per-quarter rolling forecast errors", loc="left")
save(fig, 28, "Per_Quarter_Errors", "Per-quarter rolling forecast errors (actual − predicted)")

fig, ax = plt.subplots(figsize=(9, 4))
groups = [err[err["Model"] == m]["Error"].values for m in models]
bp = ax.boxplot(groups, patch_artist=True, tick_labels=[m.replace(" + exog ", "\n+ exog\n") for m in models])
for patch, m in zip(bp["boxes"], models):
    patch.set_facecolor(MODEL_COLORS[m]); patch.set_alpha(0.4)
ax.axhline(0, color="#52677F", lw=0.8); ax.yaxis.set_major_formatter(MILLION); ax.tick_params(axis="x", labelsize=8)
ax.set_title("Distribution of rolling forecast errors", loc="left"); ax.set_ylabel("Actual − predicted")
save(fig, 29, "Error_Distribution", "Distribution of rolling forecast errors by model")

configs = [fc.SarimaxConfig(o, (*so, 4)) for o, so in [((1, 1, 0), (0, 1, 0)), ((0, 1, 1), (0, 1, 0)), ((0, 1, 0), (0, 1, 0)),
                                                         ((1, 1, 1), (1, 1, 0)), ((0, 1, 1), (0, 1, 1)), ((1, 1, 0), (1, 1, 0))]]
screen = ev.screen_sarimax(q, "PaxToIndia", configs, 12, 4)
R["screening"] = table(screen[["Configuration", "Successful forecasts", "MAE", "RMSE", "MAPE (%)"]])
fig, ax = plt.subplots(figsize=(10, 3.8))
ax.barh(screen["Configuration"][::-1], screen["MAE"][::-1], color=COLORS["primary"])
for i, v in enumerate(screen["MAE"][::-1]):
    ax.text(v, i, f" {v:,.0f}", va="center", fontsize=8)
ax.axvline(met.loc[fc.NAIVE, "MAE"], color=MODEL_COLORS[fc.NAIVE], ls="--", label="Seasonal Naive MAE")
ax.xaxis.set_major_formatter(MILLION); ax.legend(frameon=False, loc="lower right"); ax.set_xlabel("MAE")
ax.set_title("SARIMAX order screening on the rolling window", loc="left")
save(fig, 30, "SARIMAX_Order_Screening", "Rolling-origin MAE of alternative SARIMAX orders")

suit = fc.var_suitability(q, vcfg)
R["var"] = {"lag_cap": suit["lag_cap"], "n_transformed": suit["n_transformed"], "adf": table(suit["adf"]), "notes": suit["notes"]}

fut = {m: fc.run_forecast(m, q, "PaxToIndia", 8, 95, 4, scfg, vcfg) for m in [fc.NAIVE, fc.SARIMAX, fc.VAR_MODEL, fc.EXOG_OPERATIONAL]}
fut_log = fc.sarimax_forecast(pax, 8, fc.SarimaxConfig(log=True), 95)
R["var"]["spec"] = fut[fc.VAR_MODEL].spec
R["var"]["aic"] = fut[fc.VAR_MODEL].aic
R["future"] = {m: table(r.forecast.reset_index()) for m, r in fut.items()}
R["future_log"] = table(fut_log.forecast.reset_index())
R["future_checks"] = table(fc.validate_forecast(fut[fc.SARIMAX].forecast, q.index, 8))
R["future_notes"] = {m: r.warnings + r.notes for m, r in fut.items()}


def forecast_plot(num, res, slug, title, caption):
    fig, ax = plt.subplots(figsize=(10, 4.3))
    h = pax.iloc[-24:]
    fcast = res.forecast
    xs = [h.index[-1], *fcast.index]
    ax.plot(h.index, h, color=COLORS["text"], lw=2, marker="o", ms=3, label="Observed")
    ax.fill_between(xs, [h.iloc[-1], *fcast["Lower"]], [h.iloc[-1], *fcast["Upper"]], color=COLORS["primary"], alpha=0.15, label="95% prediction interval")
    ax.plot(xs, [h.iloc[-1], *fcast["Forecast"]], color=COLORS["primary"], lw=2.4, ls="--", marker="o", ms=4, label="Point forecast")
    ax.axvline(h.index[-1] + pd.Timedelta(days=45), color="#62748A", ls=":")
    ax.axhline(0, color="#B91C1C", lw=0.7, alpha=0.6)
    ax.yaxis.set_major_formatter(MILLION); ax.legend(frameon=False, loc="upper left", fontsize=8.5); ax.set_ylabel("Passengers")
    ax.set_title(title, loc="left")
    save(fig, num, slug, caption)


forecast_plot(31, fut[fc.SARIMAX], "Future_Forecast_SARIMAX", "8-quarter forecast – SARIMAX(1,1,1)(1,1,0,4)",
              "Eight-quarter forecast of passengers to India from SARIMAX(1,1,1)(1,1,0,4) with 95% prediction interval")
forecast_plot(32, fut_log, "Future_Forecast_Log_SARIMAX", "8-quarter forecast – SARIMAX on log values",
              "Eight-quarter forecast from SARIMAX fitted to log values, with 95% prediction interval")

fig, ax = plt.subplots(figsize=(10, 4.2))
h = pax.iloc[-12:]
ax.plot(h.index, h, color=COLORS["text"], lw=2.4, marker="o", label="Observed")
for m, r in fut.items():
    xs = [h.index[-1], *r.forecast.index]
    ax.plot(xs, [h.iloc[-1], *r.forecast["Forecast"]], color=MODEL_COLORS[m], lw=2, ls="--", marker="s", ms=4, label=m)
ax.yaxis.set_major_formatter(MILLION); ax.legend(frameon=False, fontsize=8.5, ncol=2); ax.set_ylabel("Passengers")
ax.set_title("Point forecasts of the four future-capable models", loc="left")
save(fig, 33, "Future_Forecast_Model_Comparison", "Comparison of eight-quarter point forecasts from the four future-capable models")

fig, ax = plt.subplots(figsize=(10, 3.8))
hzn = np.arange(1, 9)
for m, r in list(fut.items()) + [("SARIMAX (log)", fut_log)]:
    width = (r.forecast["Upper"] - r.forecast["Lower"]) / r.forecast["Forecast"] * 100
    ax.plot(hzn, width, marker="o", lw=2, label=m, color=MODEL_COLORS.get(m, "#0EA5E9"))
ax.set_xlabel("Forecast horizon (quarters ahead)"); ax.set_ylabel("Interval width (% of forecast)")
ax.legend(frameon=False, fontsize=8.5, ncol=2); ax.set_title("Growth of 95% interval width with horizon", loc="left")
save(fig, 34, "Interval_Width_by_Horizon", "Width of the 95% prediction interval relative to the point forecast, by horizon")

# =========================================================================== residuals
resid = full.residuals
R["resid_summary"] = {k: (float(v) if isinstance(v, (int, float, np.floating)) else v) for k, v in dg.residual_summary(resid).items()}
R["resid_lb"] = table(dg.ljung_box(resid, [4, 8], model_df=3))
fig, axes = plt.subplots(2, 2, figsize=(11, 7))
ax = axes[0, 0]; ax.plot(resid.index, resid, marker="o", color=COLORS["primary"]); ax.axhline(0, color="#52677F", ls="--")
ax.set_title("Residuals over time", loc="left"); ax.yaxis.set_major_formatter(MILLION)
ax = axes[0, 1]; ax.hist(resid, bins=12, color=COLORS["primary"], edgecolor="white"); ax.set_title("Histogram", loc="left")
ax.xaxis.set_major_formatter(MILLION)
ax = axes[1, 0]; qp = dg.qq_points(resid); ax.scatter(qp["Theoretical"], qp["Sample"], color=COLORS["primary"], s=16)
ax.plot(qp["Theoretical"], qp["Line"], color=COLORS["warning"], ls="--"); ax.set_title("Normal Q-Q plot", loc="left")
ax.yaxis.set_major_formatter(MILLION); ax.set_xlabel("Theoretical quantiles")
ax = axes[1, 1]; va = dg.acf_pacf(resid, 10); b = va["Bound"].iloc[0]
ax.vlines(va["Lag"][1:], 0, va["ACF"][1:], color=COLORS["primary"], lw=2); ax.axhspan(-b, b, color=COLORS["sky"], alpha=0.18)
ax.axhline(0, color="#52677F", lw=0.8); ax.set_title("Residual ACF", loc="left"); ax.set_xlabel("Lag")
fig.suptitle("SARIMAX(1,1,1)(1,1,0,4) in-sample residual diagnostics", x=0.02, ha="left", fontweight="bold")
fig.tight_layout()
save(fig, 35, "SARIMAX_Residual_Diagnostics", "In-sample residual diagnostics of SARIMAX(1,1,1)(1,1,0,4)")

re = (f["Actual"] - f[fc.SARIMAX])
R["roll_err_summary"] = {k: (float(v) if isinstance(v, (int, float, np.floating)) else v) for k, v in dg.residual_summary(re).items()}
R["roll_err_lb"] = table(dg.ljung_box(re, [4]))
fig, axes = plt.subplots(1, 3, figsize=(12, 3.6))
axes[0].bar(re.index, re.values, width=60, color=[COLORS["positive"] if v > 0 else COLORS["negative"] for v in re])
axes[0].axhline(0, color="#52677F", lw=0.8); axes[0].set_title("Errors over time", loc="left"); axes[0].yaxis.set_major_formatter(MILLION)
axes[0].tick_params(axis="x", rotation=45, labelsize=8)
axes[1].hist(re, bins=6, color=COLORS["primary"], edgecolor="white"); axes[1].set_title("Histogram", loc="left"); axes[1].xaxis.set_major_formatter(MILLION)
qp = dg.qq_points(re); axes[2].scatter(qp["Theoretical"], qp["Sample"], color=COLORS["primary"])
axes[2].plot(qp["Theoretical"], qp["Line"], color=COLORS["warning"], ls="--"); axes[2].set_title("Normal Q-Q plot", loc="left")
axes[2].yaxis.set_major_formatter(MILLION)
fig.suptitle("SARIMAX rolling forecast errors (actual − predicted, n = 12)", x=0.02, ha="left", fontweight="bold")
fig.tight_layout()
save(fig, 36, "SARIMAX_Rolling_Error_Diagnostics", "Diagnostics of SARIMAX rolling-origin forecast errors")

# =========================================================================== schedule gantt
tasks = [("Problem identification & literature review", 0, 2), ("Data collection & validation", 2, 2),
         ("Exploratory data analysis", 3, 2), ("Stationarity & seasonality analysis", 4, 2), ("Model development (Naive, SARIMAX, VAR)", 5, 3),
         ("Rolling-origin evaluation", 7, 2), ("Dashboard development", 7, 5), ("Testing & validation", 11, 2),
         ("Report writing", 12, 4), ("Final review", 16, 1)]
fig, ax = plt.subplots(figsize=(10, 4.2))
for i, (t, s, d) in enumerate(tasks):
    ax.barh(i, d, left=s, color=["#2563EB", "#0D9488", "#F59E0B", "#7C3AED", "#DB2777"][i % 5], alpha=0.85)
ax.set_yticks(range(len(tasks)), [t for t, _, _ in tasks], fontsize=8.5); ax.invert_yaxis()
ax.set_xticks(range(0, 18, 2), ["Jul W1", "Jul W3", "Aug W1", "Aug W3", "Sep W1", "Sep W3", "Oct W1", "Oct W3", "Nov W1"], fontsize=8.5)
ax.set_title("Project schedule (weeks, July – November 2026)", loc="left")
save(fig, 37, "Project_Schedule_Gantt", "Project schedule as a Gantt chart")

R["figures"] = FIGURES
(ROOT / "thesis" / "results.json").write_text(json.dumps(R, indent=1, default=lambda o: None if isinstance(o, float) and not np.isfinite(o) else str(o)))
print(f"{len(FIGURES)} figures written to {FIG}")
