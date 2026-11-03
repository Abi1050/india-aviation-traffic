import pandas as pd
import streamlit as st

from config import settings
from config.settings import FREIGHT_COLUMNS, LABELS, PASSENGER_COLUMNS, TRAFFIC_COLUMNS
from src import data_loader, eda, state, ui, visualization as viz
from src.utils import fmt_number, quarter_label
from src.validation import SCHEMA_HELP, SchemaError

ui.page_header("Dataset Explorer",
               "Load, validate and inspect the international aviation traffic records behind every analysis.",
               eyebrow="Data & analysis")

# --------------------------------------------------------------------------- source selection
ui.section("Data source", "Local files are used by default; nothing is sent over the network unless you request a refresh.")
options = [data_loader.SOURCE_COUNTRY, data_loader.SOURCE_QUARTERLY, data_loader.SOURCE_UPLOAD, data_loader.SOURCE_REMOTE]
current = st.session_state.get("bundle")
choice = st.radio("Choose a data source", options, horizontal=True,
                  index=options.index(current.source) if current is not None and current.source in options else 0)
if choice == data_loader.SOURCE_COUNTRY:
    st.caption(f"`{settings.COUNTRY_CSV}` – one row per country and quarter (supports country filters).")
    if st.button("Use local country-level source", type="primary"):
        try:
            state.use_local(choice)
            st.success("Country-level source loaded.")
            st.rerun()
        except data_loader.DataLoadError as exc:
            st.error(f"Could not load the file; the previous dataset is kept. {exc}")
elif choice == data_loader.SOURCE_QUARTERLY:
    st.caption(f"`{settings.QUARTERLY_CSV}` – notebook output with one row per quarter (no country detail).")
    if st.button("Use local quarterly aggregate", type="primary"):
        try:
            state.use_local(choice)
            st.success("Quarterly aggregate loaded.")
            st.rerun()
        except data_loader.DataLoadError as exc:
            st.error(f"Could not load the file; the previous dataset is kept. {exc}")
elif choice == data_loader.SOURCE_UPLOAD:
    uploaded = st.file_uploader(f"Upload a CSV (max {settings.MAX_UPLOAD_MB} MB)", type=["csv"])
    with st.expander("Accepted layouts"):
        st.code(SCHEMA_HELP, language=None)
    if uploaded is not None and st.button("Validate and use this file", type="primary"):
        try:
            state.set_bundle(data_loader.load_upload(uploaded.getvalue(), uploaded.name))
            st.success(f"{uploaded.name} validated and loaded.")
            st.rerun()
        except (SchemaError, data_loader.DataLoadError) as exc:
            st.error(f"The file was not loaded; the previous dataset is kept.\n\n{exc}")
else:
    st.caption(f"Downloads `country.csv` from [{settings.REMOTE_REPO_URL}]({settings.REMOTE_REPO_URL}). "
               "The download is kept in this session only; local files are not modified.")
    if st.button("Download latest data", type="primary", icon=":material/cloud_download:"):
        try:
            with st.spinner("Downloading…"):
                state.set_bundle(data_loader.fetch_remote())
            st.success("Remote data downloaded and validated.")
            st.rerun()
        except (SchemaError, data_loader.DataLoadError) as exc:
            st.error(f"Refresh failed; the last successfully loaded dataset is kept. {exc}")

ctx = state.get_context()
ui.no_data_stop(ctx)
b = ctx.bundle
st.info(f"Active dataset: **{b.filename}** · {b.source} · loaded {b.loaded_at}")

# --------------------------------------------------------------------------- overview
raw = b.raw
q_all = b.quarterly
cards = [
    ui.kpi_card("Rows (raw file)", fmt_number(len(raw)), f"{len(b.records):,} valid records used", accent=True),
    ui.kpi_card("Columns", str(raw.shape[1]), ", ".join(map(str, raw.columns[:4])) + ("…" if raw.shape[1] > 4 else "")),
    ui.kpi_card("Historical coverage", f"{len(q_all)} quarters",
                f"{quarter_label(q_all.index.min())} – {quarter_label(q_all.index.max())}"),
    ui.kpi_card("Countries", str(len(b.countries)) if b.has_country else "n/a",
                "Unique countries" if b.has_country else "Aggregated file – no country detail"),
    ui.kpi_card("Missing values", fmt_number(int(raw.isna().sum().sum())), "Across all raw columns"),
    ui.kpi_card("Duplicate rows", fmt_number(int(raw.duplicated().sum())), "Exact duplicates in the raw file"),
    ui.kpi_card("Excluded records", fmt_number(len(b.excluded)), "See the data-quality tab"),
    ui.kpi_card("Latest quarter", b.latest.get("label", "–"), b.latest.get("status", "")),
]
ui.kpi_row(cards, 4)

tab_quality, tab_records, tab_quarterly, tab_raw, tab_charts = st.tabs(
    ["Data quality", "Records", "Quarterly totals", "Raw file & structure", "Charts"])

with tab_quality:
    ui.section("Data-quality report", "Every check, what it found and what was done. No record is dropped silently.")
    ui.table(b.quality)
    if b.latest:
        st.markdown("**Latest-quarter completeness evidence**")
        for line in b.latest.get("evidence", []):
            st.markdown(f"- ✅ {line}")
        for line in b.latest.get("concerns", []):
            st.markdown(f"- ⚠️ {line}")
    st.markdown("**Excluded records**")
    if b.excluded.empty:
        st.success("No records were excluded.")
    else:
        ui.table(b.excluded, height=260)
    c1, c2 = st.columns(2)
    c1.download_button("Download data-quality report (CSV)", b.quality.to_csv(index=False).encode(),
                       "data_quality_report.csv", "text/csv", icon=":material/download:")
    if not b.excluded.empty:
        c2.download_button("Download excluded records (CSV)", b.excluded.to_csv(index=False).encode(),
                           "excluded_records.csv", "text/csv", icon=":material/download:")

with tab_records:
    ui.section("Quarterly aviation traffic records", f"Filtered by the sidebar: {ctx.filter_note}.")
    c1, c2 = st.columns([1, 2])
    category = c1.segmented_control("Traffic category", ["All", "Passenger", "Freight"], default="All",
                                    key="dx_category") or "All"
    pool = {"All": TRAFFIC_COLUMNS, "Passenger": PASSENGER_COLUMNS, "Freight": FREIGHT_COLUMNS}[category]
    chosen = c2.multiselect("Traffic variables", pool, default=pool, format_func=lambda c: LABELS[c], key=f"dx_vars_{category}")
    id_cols = ["Date", "Year", "Quarter"] + (["Country"] if b.has_country else [])
    shown = ctx.records[id_cols + (chosen or pool)]
    st.caption(f"{len(shown):,} rows × {shown.shape[1]} columns")
    ui.table(shown, height=420)
    st.download_button("Download filtered records (CSV)", shown.to_csv(index=False, date_format="%Y-%m-%d").encode(),
                       "filtered_aviation_records.csv", "text/csv", icon=":material/download:")

with tab_quarterly:
    ui.section("Quarterly totals", "One row per quarter after filtering, summed once from the records.")
    qt = ctx.quarterly.reset_index()
    qt.insert(1, "Period", [quarter_label(d) for d in qt["Date"]])
    ui.table(qt, height=420)
    c1, c2 = st.columns(2)
    c1.download_button("Download quarterly totals (CSV)", qt.to_csv(index=False, date_format="%Y-%m-%d").encode(),
                       "quarterly_aviation_traffic_filtered.csv", "text/csv", icon=":material/download:")
    c2.download_button("Download full cleaned records (CSV)", b.records.to_csv(index=False, date_format="%Y-%m-%d").encode(),
                       "cleaned_aviation_records.csv", "text/csv", icon=":material/download:")
    ui.section("Summary statistics", "Computed on the filtered quarterly totals.")
    ui.table(eda.descriptive_statistics(ctx.quarterly, TRAFFIC_COLUMNS),
             number_format={c: "localized" for c in ["Mean", "Median", "Std. dev.", "Min", "Q1", "Q3", "Max"]}
             | {"Skewness": "%.3f", "Kurtosis": "%.3f", "CV (%)": "%.1f"})

with tab_raw:
    c1, c2 = st.columns(2)
    with c1:
        ui.section("First records")
        st.dataframe(raw.head(10), width="stretch", hide_index=True)
    with c2:
        ui.section("Last records")
        st.dataframe(raw.tail(10), width="stretch", hide_index=True)
    ui.section("Column structure")
    struct = pd.DataFrame({"Column": raw.columns.astype(str), "Data type": raw.dtypes.astype(str).values,
                           "Non-null": raw.notna().sum().values, "Missing": raw.isna().sum().values,
                           "Unique values": raw.nunique().values})
    ui.table(struct)

with tab_charts:
    c1, c2 = st.columns(2)
    with c1:
        missing = ctx.records[TRAFFIC_COLUMNS].isna().sum()
        fig = viz.bar_chart([LABELS[c] for c in missing.index], missing.values, "Missing Values by Variable",
                            "Variable", "Missing records", color=viz.COLORS["warning"], text_format="%{y}")
        ui.chart(fig)
        if missing.sum() == 0:
            st.caption("No missing values in the filtered records.")
    with c2:
        ui.chart(viz.histogram(ctx.quarterly["PaxToIndia"].dropna(), "Passenger Traffic Distribution",
                               "Passengers to India per quarter", nbins=15))
    if b.has_country and not ctx.records.empty:
        top = eda.top_countries(ctx.records, ctx.target, 15)
        ui.chart(viz.bar_chart(top["Country"], top["Total"], f"Top 15 Countries by {LABELS[ctx.target]}",
                               "Country", f"Total {LABELS[ctx.target].lower()}", horizontal=True, height=480))
