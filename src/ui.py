"""Shared page furniture: CSS, headers, KPI cards, sidebar and table helpers."""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from config import settings
from config.settings import COLORS, LABELS
from src import state
from src.utils import fmt_number, quarter_label, quarter_labels, slugify

CSS = f"""
<style>
.block-container {{ padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1440px; }}
.page-header {{ margin: 0 0 1.1rem 0; padding-bottom: .8rem; border-bottom: 1px solid {COLORS['border']}; }}
.page-header .eyebrow {{ color: {COLORS['primary']}; font-size: .78rem; font-weight: 700; letter-spacing: .08em;
  text-transform: uppercase; margin-bottom: .2rem; }}
.page-header h1 {{ color: {COLORS['text']}; font-size: 1.95rem; font-weight: 750; margin: 0; padding: 0; line-height: 1.2; }}
.page-header p {{ color: {COLORS['text_secondary']}; font-size: 1rem; margin: .35rem 0 0 0; }}
.section-title {{ color: {COLORS['text']}; font-size: 1.12rem; font-weight: 700; margin: 1.3rem 0 .15rem 0;
  padding-left: .6rem; border-left: 4px solid {COLORS['primary']}; }}
.section-caption {{ color: {COLORS['text_secondary']}; font-size: .9rem; margin: 0 0 .6rem .9rem; }}
.kpi-card {{ background: {COLORS['card']}; border: 1px solid {COLORS['border']}; border-radius: 12px;
  padding: .85rem 1rem .8rem 1rem; box-shadow: 0 1px 2px rgba(16,24,40,.05); min-height: 118px; margin-bottom: .75rem; }}
.kpi-card.accent {{ border-top: 3px solid {COLORS['primary']}; }}
.kpi-label {{ color: {COLORS['text_muted']}; font-size: .74rem; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; }}
.kpi-value {{ color: {COLORS['text']}; font-size: 1.55rem; font-weight: 750; margin: .2rem 0 .1rem 0; line-height: 1.2;
  overflow-wrap: anywhere; }}
.kpi-sub {{ color: {COLORS['text_secondary']}; font-size: .8rem; line-height: 1.35; }}
.kpi-delta {{ font-weight: 700; }}
.kpi-delta.pos {{ color: {COLORS['positive']}; }} .kpi-delta.neg {{ color: {COLORS['negative']}; }}
.kpi-delta.neu {{ color: {COLORS['text_muted']}; }}
.insight {{ background: {COLORS['card']}; border: 1px solid {COLORS['border']}; border-left: 4px solid {COLORS['positive']};
  border-radius: 10px; padding: .55rem .85rem; margin-bottom: .45rem; color: {COLORS['text']}; font-size: .93rem; }}
.insight.warn {{ border-left-color: {COLORS['warning']}; }}
.pill {{ display: inline-block; padding: .08rem .55rem; border-radius: 999px; font-size: .75rem; font-weight: 700; }}
.pill.ok {{ background: #CCFBF1; color: #115E59; }} .pill.warn {{ background: #FEF3C7; color: #92400E; }}
.pill.bad {{ background: #FEE2E2; color: #991B1B; }} .pill.info {{ background: #DBEAFE; color: #1E3A8A; }}
[data-testid="stPlotlyChart"] {{ background: #FFFFFF; border: 1px solid {COLORS['border']}; border-radius: 12px;
  padding: 4px 6px; box-shadow: 0 1px 2px rgba(16,24,40,.04); }}
[data-testid="stTabs"] button[role="tab"] p {{ font-weight: 600; font-size: .95rem; }}
[data-testid="stMetric"] {{ background: #FFFFFF; border: 1px solid {COLORS['border']}; border-radius: 12px; padding: .6rem .9rem; }}
/* sidebar */
.side-brand {{ padding: .2rem 0 .8rem 0; border-bottom: 1px solid #24456A; margin-bottom: .8rem; }}
.side-brand .top {{ color: #7DD3FC; font-size: .78rem; font-weight: 800; letter-spacing: .14em; }}
.side-brand .name {{ color: #FFFFFF; font-size: 1.25rem; font-weight: 750; line-height: 1.25; }}
.side-brand .tag {{ color: #A9BCD0; font-size: .8rem; margin-top: .15rem; }}
.side-card {{ background: #13304D; border: 1px solid #24456A; border-radius: 10px; padding: .65rem .8rem; margin-bottom: .8rem; }}
.side-card .row {{ display: flex; justify-content: space-between; gap: .6rem; font-size: .8rem; padding: .12rem 0; }}
.side-card .k {{ color: #A9BCD0; }} .side-card .v {{ color: #FFFFFF; font-weight: 600; text-align: right; overflow-wrap: anywhere; }}
.side-section {{ color: #7DD3FC; font-size: .72rem; font-weight: 800; letter-spacing: .12em; text-transform: uppercase;
  margin: .9rem 0 .25rem 0; }}
.side-note {{ color: #C9D6E3; font-size: .8rem; line-height: 1.45; }}
@media (max-width: 900px) {{ .kpi-value {{ font-size: 1.3rem; }} .page-header h1 {{ font-size: 1.55rem; }} }}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str, eyebrow: str = "Civil Aviation Analytics") -> None:
    st.markdown(
        f"<div class='page-header'><div class='eyebrow'>{html.escape(eyebrow)}</div>"
        f"<h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></div>", unsafe_allow_html=True)


def section(title: str, caption: str | None = None) -> None:
    st.markdown(f"<div class='section-title'>{html.escape(title)}</div>", unsafe_allow_html=True)
    if caption:
        st.markdown(f"<div class='section-caption'>{html.escape(caption)}</div>", unsafe_allow_html=True)


def kpi_card(label: str, value: str, sub: str = "", delta: str | None = None, tone: str = "neu",
             accent: bool = False) -> str:
    delta_html = f"<span class='kpi-delta {tone}'>{html.escape(delta)}</span> " if delta else ""
    return (f"<div class='kpi-card{' accent' if accent else ''}'><div class='kpi-label'>{html.escape(label)}</div>"
            f"<div class='kpi-value'>{html.escape(value)}</div><div class='kpi-sub'>{delta_html}{html.escape(sub)}</div></div>")


def kpi_row(cards: list[str], columns: int = 4) -> None:
    for start in range(0, len(cards), columns):
        cols = st.columns(columns)
        for col, card in zip(cols, cards[start:start + columns]):
            col.markdown(card, unsafe_allow_html=True)


def tone_for(value: float) -> str:
    try:
        return "pos" if value > 0 else "neg" if value < 0 else "neu"
    except TypeError:
        return "neu"


def insights(lines: list[str], warn: bool = False) -> None:
    for line in lines:
        st.markdown(f"<div class='insight{' warn' if warn else ''}'>{html.escape(line)}</div>", unsafe_allow_html=True)


def pill(text: str, kind: str = "info") -> str:
    return f"<span class='pill {kind}'>{html.escape(text)}</span>"


PLOTLY_CONFIG = {"displaylogo": False, "responsive": True,
                 "modeBarButtonsToRemove": ["lasso2d", "select2d"]}


def chart(fig, key: str | None = None, filename: str | None = None) -> None:
    config = dict(PLOTLY_CONFIG)
    title = fig.layout.title.text or "chart"
    config["toImageButtonOptions"] = {"format": "png", "scale": 2,
                                      "filename": filename or slugify(title.split("<br>")[0].replace("<b>", "").replace("</b>", ""))}
    st.plotly_chart(fig, width="stretch", theme=None, config=config, key=key)


def column_config(df: pd.DataFrame) -> dict:
    """Readable display labels and number formats without renaming the data."""
    cfg = {}
    for col in df.columns:
        label = LABELS.get(col, col)
        if col == "Date" or pd.api.types.is_datetime64_any_dtype(df[col]):
            cfg[col] = st.column_config.DateColumn(label if col == "Date" else col, format="YYYY-MM-DD")
        elif col.startswith(("Pax", "Freight")) and pd.api.types.is_numeric_dtype(df[col]):
            cfg[col] = st.column_config.NumberColumn(label, format="localized")
        elif col in ("Year", "Quarter"):
            cfg[col] = st.column_config.NumberColumn(label, format="%d")
        elif col in LABELS:
            cfg[col] = st.column_config.Column(label)
    return cfg


def table(df: pd.DataFrame, height: int | str = "auto", hide_index: bool = True, number_format: dict | None = None,
          key: str | None = None) -> None:
    # Display-only rounding: large counts without decimals, small values with two.
    df = df.copy()
    explicit = number_format or {}
    for col in df.columns:
        if pd.api.types.is_float_dtype(df[col]) and explicit.get(col, "localized") == "localized":
            df[col] = df[col].round(0 if df[col].abs().max() >= 10_000 else 2)
    cfg = column_config(df)
    for col, fmt in (number_format or {}).items():
        if col in df.columns:
            cfg[col] = st.column_config.NumberColumn(LABELS.get(col, col), format=fmt)
    st.dataframe(df, width="stretch", height=height, hide_index=hide_index, column_config=cfg, key=key)


def no_data_stop(ctx) -> None:
    if ctx is None:
        st.error("No dataset is loaded. " + st.session_state.get("bundle_error", ""))
        st.info(f"Place `country.csv` in `{settings.DATA_DIR}` or set the `AVIATION_DATA_DIR` environment variable, "
                "then use **Reload dataset** in the sidebar, or upload a CSV on the Dataset Explorer page.")
        st.stop()
    if ctx.quarterly.dropna(how="all").empty:
        st.warning("The current filters leave no observations. Widen the date range or country selection.")
        st.stop()


# --------------------------------------------------------------------------- sidebar
def _card_rows(rows: list[tuple[str, str]]) -> str:
    return "".join(f"<div class='row'><span class='k'>{html.escape(k)}</span><span class='v'>{html.escape(v)}</span></div>"
                   for k, v in rows)


def render_sidebar(page_groups: dict) -> None:
    bundle = state.get_bundle()
    with st.sidebar:
        st.markdown("<div class='side-brand'><div class='top'>✈ CIVIL AVIATION</div>"
                    "<div class='name'>Analytics Platform</div>"
                    "<div class='tag'>International Passenger &amp; Freight Traffic</div></div>", unsafe_allow_html=True)
        if bundle is None:
            st.error("No dataset loaded")
        else:
            q = bundle.quarterly
            issues = bundle.quality["Status"].isin(["Fail", "Warning"]).sum()
            status = "Validated" if issues == 0 else f"Loaded · {issues} warning(s)"
            rows = [("Status", status), ("File", bundle.filename), ("Source", bundle.source),
                    ("Coverage", f"{quarter_label(q.index.min())} – {quarter_label(q.index.max())}" if len(q) else "–"),
                    ("Quarters", str(int(q.dropna(how='all').shape[0]))),
                    ("Traffic variables", str(len(settings.TRAFFIC_COLUMNS)))]
            if bundle.has_country:
                rows.append(("Countries", str(len(bundle.countries))))
            rows += [("Latest quarter", f"{bundle.latest.get('label', '–')} · {bundle.latest.get('status', '')}"),
                     ("Last refresh", bundle.loaded_at)]
            st.markdown(f"<div class='side-card'>{_card_rows(rows)}</div>", unsafe_allow_html=True)

        for group, pages in page_groups.items():
            st.markdown(f"<div class='side-section'>{html.escape(group)}</div>", unsafe_allow_html=True)
            for page in pages:
                st.page_link(page, width="stretch")

        if bundle is not None:
            labels = quarter_labels(bundle.quarterly.index)
            st.markdown("<div class='side-section'>Data filters</div>", unsafe_allow_html=True)
            if len(labels) > 1:
                c1, c2 = st.columns(2)
                c1.selectbox("From", labels, key="flt_start")
                c2.selectbox("To", labels, key="flt_end")
            if bundle.has_country:
                st.multiselect("Countries", bundle.countries, key="flt_countries", placeholder="All countries",
                               help="Leave empty to include all countries. Records are filtered before quarterly "
                                    "aggregation, so nothing is counted twice.")
            st.markdown("<div class='side-section'>Forecast settings</div>", unsafe_allow_html=True)
            st.selectbox("Target variable", settings.TRAFFIC_COLUMNS, key="cfg_target",
                         format_func=lambda c: LABELS[c])
            st.slider("Forecast horizon (quarters)", 1, 16, key="cfg_horizon")
            st.select_slider("Confidence level (%)", options=[80, 90, 95, 99], key="cfg_ci")
            st.number_input("Seasonal period (quarters)", 1, 8, step=1, key="cfg_period",
                            help="Quarterly data repeat every 4 quarters; change only for experiments.")
            st.toggle("Show markers on charts", key="cfg_markers")

        if st.button("Reload dataset", icon=":material/refresh:", width="stretch"):
            st.toast(state.reload_dataset())
            st.rerun()
        st.markdown("<div class='side-section'>Target variable</div>"
                    "<div class='side-note'><b>PaxToIndia</b> – international passengers arriving in India per "
                    "quarter. Other passenger and freight series support analysis and multivariate models.</div>"
                    "<div class='side-section'>Data source</div>"
                    f"<div class='side-note'>DGCA international traffic compiled by "
                    f"<a href='{settings.REMOTE_REPO_URL}' target='_blank' style='color:#7DD3FC'>Vonter/india-aviation-traffic</a>.</div>",
                    unsafe_allow_html=True)
