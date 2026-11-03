"""Integration tests: every page is rendered through the real app shell with Streamlit's AppTest."""

import zipfile
from io import BytesIO

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src import artifacts, reporting
from src.shell import PAGE_FILES, ROOT


def app_for(page: str) -> AppTest:
    script = f"import sys\nsys.path.insert(0, r'{ROOT}')\nfrom src.shell import run_app\nrun_app({page!r})\n"
    return AppTest.from_string(script, default_timeout=300)


@pytest.mark.parametrize("page", PAGE_FILES)
def test_page_renders_without_exceptions(page):
    at = app_for(page).run()
    assert not at.exception, [e.message for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    # sidebar status card and filters render on every page
    assert any(s.label == "Target variable" for s in at.selectbox)


def test_dashboard_kpis_and_charts():
    at = app_for("1_Executive_Dashboard.py").run()
    assert len(at.get("plotly_chart")) >= 6
    html = " ".join(m.value for m in at.markdown)
    for label in ["Total passengers to India", "Best evaluated model", "Forecast horizon", "2026 Q2"]:
        assert label in html


@pytest.mark.parametrize("model", ["Seasonal Naive", "SARIMAX", "VAR", "SARIMAX + exog (operational)"])
def test_forecasting_lab_models(model):
    at = app_for("5_Forecasting_Laboratory.py")
    at.session_state["lab_model"] = model
    at.run()
    assert not at.exception and not at.error, [e.value for e in at.error]
    assert len(at.get("plotly_chart")) >= 2


def test_country_filter_changes_results():
    at = app_for("2_Dataset_Explorer.py").run()
    at.multiselect(key="flt_countries").set_value(["UNITED ARAB EMIRATES"]).run()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)
    assert "1 selected countries" in text
    # spelling variants are harmonised, so the UAE has a full series
    assert "46 rows" in text


def test_report_package_generation():
    at = app_for("9_Reports_and_Downloads.py").run()
    next(b for b in at.button if b.label == "Generate report package").click().run()
    assert not at.exception, [e.message for e in at.exception]
    pkg = at.session_state["report_pkg"]
    assert pkg["pdf"][:4] == b"%PDF"
    assert not pkg["failures"]
    names = zipfile.ZipFile(BytesIO(pkg["zip"])).namelist()
    for required in ["report/civil_aviation_report.pdf", "report/civil_aviation_report.md",
                     "evaluation/model_comparison.csv", "forecast/future_forecast.csv",
                     "data/data_quality_report.csv", "charts/future_forecast.png"]:
        assert required in names
    assert not any("review" in n.lower() for n in names)
    for n in range(1, 17):
        assert f"## {n}. " in pkg["md"]


def test_future_forecast_pdf_button():
    at = app_for("7_Future_Forecast.py").run()
    next(b for b in at.button if b.label == "Build PDF report").click().run()
    assert not at.exception
    assert at.session_state["ff_pdf"][1][:4] == b"%PDF"


def test_missing_output_folder_handled(tmp_path):
    assert artifacts.list_artifacts(tmp_path / "does_not_exist").empty
    assert artifacts.read_csv("anything.csv", tmp_path) is None


def test_artifact_names_hide_review_prefix():
    assert artifacts.display_name("review3_final_validation_metrics.csv") == "final_validation_metrics.csv"
    assert artifacts.display_name("_final_8_quarter_forecast.png") == "final_8_quarter_forecast.png"
    assert artifacts.display_name("review2_model_comparison.csv") == "rolling_three_model_comparison.csv"
    assert artifacts.display_name("model_comparison.csv") == "model_comparison.csv"
    lib = artifacts.list_artifacts()
    assert not lib["Display name"].str.contains("review", case=False).any()
    assert lib["Display name"].is_unique


def test_markdown_tables_render_missing_values():
    assert "_Not available._" in reporting._md_table(pd.DataFrame())


@pytest.mark.parametrize("source", ["Local country-level source", "Local quarterly aggregate"])
def test_switching_data_source_resets_filters(source):
    """Regression: activating a dataset must not modify filter widgets after they are drawn."""
    at = app_for("2_Dataset_Explorer.py").run()
    at.multiselect(key="flt_countries").set_value(["UNITED ARAB EMIRATES"]).run()
    at.radio[0].set_value(source).run()
    next(b for b in at.button if b.label.startswith("Use local")).click().run()
    assert not at.exception, [e.message for e in at.exception]
    assert at.session_state["bundle"].source == source
    assert at.session_state["flt_countries"] == []
    assert at.session_state["flt_start"] == "2015 Q1"


def test_reload_dataset_button():
    at = app_for("1_Executive_Dashboard.py").run()
    at.selectbox(key="flt_start").set_value("2018 Q1").run()
    next(b for b in at.button if b.label == "Reload dataset").click().run()
    assert not at.exception, [e.message for e in at.exception]
    assert at.session_state["flt_start"] == "2015 Q1"
