from pathlib import Path

import pandas as pd
import streamlit as st

from config import settings
from src import artifacts, report_context, reporting, state, ui

ctx = state.get_context()
ui.no_data_stop(ctx)
ui.page_header("Reports & Downloads",
               "Generate the project report from the current results and export every output.", eyebrow="Outputs")
st.caption(f"Reports reflect the current settings: {ctx.filter_note} · target {ctx.target} · "
           f"{ctx.horizon}-quarter horizon · {ctx.ci}% intervals · evaluation models: {', '.join(st.session_state['ev_models'])}.")

signature = (ctx.filter_note, ctx.target, ctx.horizon, ctx.ci, ctx.period, state.sarimax_config().label(),
             state.var_config().label(), tuple(st.session_state["ev_models"]), st.session_state["ev_test_size"],
             st.session_state["ev_metric"], st.session_state["ff_model"], ctx.bundle.loaded_at)
include_artifacts = st.checkbox("Include the notebook's output files in the ZIP (under plain names)", value=True)

if st.button("Generate report package", type="primary", icon=":material/description:"):
    progress = st.progress(0.0, "Collecting results…")
    data = report_context.assemble(ctx)
    progress.progress(0.35, "Rendering charts…")
    history = ctx.quarterly[ctx.target].dropna()
    charts, failures = reporting.build_charts(data, ctx.quarterly, history)
    progress.progress(0.65, "Writing Markdown, JSON and PDF…")
    md = reporting.markdown_report(data)
    js = reporting.json_summary(data)
    try:
        pdf = reporting.pdf_report(data, charts, failures)
        pdf_error = None
    except Exception as exc:  # noqa: BLE001 - surface the failure instead of hiding it
        pdf, pdf_error = None, str(exc)
    progress.progress(0.85, "Packaging files…")
    files = {"report/civil_aviation_report.md": md, "report/summary.json": js,
             "data/data_quality_report.csv": data["quality"].to_csv(index=False),
             "data/cleaned_records.csv": ctx.bundle.records.to_csv(index=False, date_format="%Y-%m-%d"),
             "data/quarterly_traffic_selected.csv": ctx.quarterly.to_csv(date_format="%Y-%m-%d"),
             "analysis/descriptive_statistics.csv": data["statistics"].to_csv(index=False),
             "analysis/adf_stationarity.csv": data["adf"].to_csv(index=False)}
    if pdf:
        files["report/civil_aviation_report.pdf"] = pdf
    if data["evaluation"]:
        files["evaluation/model_comparison.csv"] = data["evaluation"]["metrics"].to_csv(index=False)
        files["evaluation/rolling_origin_forecasts.csv"] = data["evaluation"]["forecasts"].to_csv(index=False, date_format="%Y-%m-%d")
    if data["forecast"]:
        files["forecast/future_forecast.csv"] = data["forecast"]["table"].to_csv(index=False, date_format="%Y-%m-%d")
        if data["forecast_checks"] is not None:
            files["forecast/forecast_validation.csv"] = data["forecast_checks"].to_csv(index=False)
    for name, png in charts.items():
        files[f"charts/{name}"] = png
    if include_artifacts:
        for _, row in artifacts.list_artifacts().iterrows():
            files[f"notebook_outputs/{row['Display name']}"] = Path(row["Path"]).read_bytes()
    st.session_state["report_pkg"] = {"signature": signature, "md": md, "json": js, "pdf": pdf, "pdf_error": pdf_error,
                                      "charts": charts, "failures": failures, "files": files,
                                      "zip": reporting.build_zip(files)}
    progress.progress(1.0, "Done")
    progress.empty()

pkg = st.session_state.get("report_pkg")
if pkg and pkg["signature"] != signature:
    st.warning("Settings changed since the report was generated. Generate it again to include the latest results.")
if pkg:
    ui.section("Downloads")
    c1, c2, c3, c4 = st.columns(4)
    c1.download_button("Report (Markdown)", pkg["md"].encode(), "civil_aviation_report.md", "text/markdown",
                       icon=":material/article:", width="stretch")
    if pkg["pdf"]:
        c2.download_button("Report (PDF)", pkg["pdf"], "civil_aviation_report.pdf", "application/pdf",
                           icon=":material/picture_as_pdf:", width="stretch")
    else:
        c2.error(f"PDF could not be created: {pkg['pdf_error']}")
    c3.download_button("Summary (JSON)", pkg["json"].encode(), "civil_aviation_summary.json", "application/json",
                       icon=":material/data_object:", width="stretch")
    c4.download_button("All outputs (ZIP)", pkg["zip"], "civil_aviation_outputs.zip", "application/zip",
                       icon=":material/folder_zip:", type="primary", width="stretch")

    ui.section("Package contents")
    contents = pd.DataFrame({"File": list(pkg["files"]),
                             "Size (KB)": [round(len(v if isinstance(v, bytes) else v.encode()) / 1024, 1)
                                           for v in pkg["files"].values()]})
    ui.table(contents, height=300)
    status = pd.DataFrame([{"Chart": n, "Status": "Exported"} for n in pkg["charts"]] +
                          [{"Chart": f.split(":")[0], "Status": "Failed – " + f.split(":", 1)[1].strip()} for f in pkg["failures"]])
    st.markdown("**Chart export status**")
    ui.table(status)

    ui.section("Report preview")
    with st.container(border=True, height=600):
        st.markdown(pkg["md"])
else:
    st.info("Click **Generate report package** to build the report from the current results.")

# --------------------------------------------------------------------------- individual files
ui.section("Individual CSV exports", "Computed live for the current selection.")
c1, c2, c3 = st.columns(3)
c1.download_button("Cleaned records", ctx.bundle.records.to_csv(index=False, date_format="%Y-%m-%d").encode(),
                   "cleaned_records.csv", "text/csv", width="stretch")
c2.download_button("Quarterly totals (selection)", ctx.quarterly.to_csv(date_format="%Y-%m-%d").encode(),
                   "quarterly_traffic_selected.csv", "text/csv", width="stretch")
c3.download_button("Data-quality report", ctx.bundle.quality.to_csv(index=False).encode(), "data_quality_report.csv",
                   "text/csv", width="stretch")

# --------------------------------------------------------------------------- notebook artifacts
ui.section("Notebook output library",
           f"Files already in `{settings.OUTPUT_DIR}`. Milestone prefixes in file names are hidden; files on disk are "
           "not renamed or modified.")
lib = artifacts.list_artifacts()
if lib.empty:
    st.info("No notebook output files were found. The dashboard computes all results itself, so this is optional.")
else:
    ui.table(lib.drop(columns=["Path"]), height=320)
    choice = st.selectbox("Preview a file", lib["Display name"])
    row = lib[lib["Display name"] == choice].iloc[0]
    path = Path(row["Path"])
    if row["Type"] == "PNG":
        st.image(str(path), caption=choice, width="stretch")
        st.download_button(f"Download {choice}", path.read_bytes(), choice, "image/png")
    else:
        df = artifacts.read_csv(choice)
        if df is None:
            st.warning("This CSV could not be read.")
        else:
            st.dataframe(df, width="stretch", hide_index=True)
            st.download_button(f"Download {choice}", path.read_bytes(), choice, "text/csv")
