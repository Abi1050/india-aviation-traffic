"""Application shell: page registry, shared state initialisation and sidebar.

``app.py`` calls :func:`run_app`. Tests call it with ``default_page`` to render a
specific page through the same shell (sidebar, state and navigation).
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src import state, ui

ROOT = Path(__file__).resolve().parents[1]

PAGES = {
    "Overview": [
        ("1_Executive_Dashboard.py", "Executive Dashboard", ":material/dashboard:"),
    ],
    "Data & analysis": [
        ("2_Dataset_Explorer.py", "Dataset Explorer", ":material/table_view:"),
        ("3_Exploratory_Analysis.py", "Exploratory Analysis", ":material/insights:"),
        ("4_Time_Series_Diagnostics.py", "Time-Series Diagnostics", ":material/query_stats:"),
    ],
    "Modelling": [
        ("5_Forecasting_Laboratory.py", "Forecasting Laboratory", ":material/science:"),
        ("6_Model_Evaluation.py", "Model Evaluation", ":material/leaderboard:"),
        ("7_Future_Forecast.py", "Future Forecast", ":material/trending_up:"),
        ("8_Residual_Analysis.py", "Residual Analysis", ":material/troubleshoot:"),
    ],
    "Outputs": [
        ("9_Reports_and_Downloads.py", "Reports & Downloads", ":material/download:"),
        ("10_Project_Methodology.py", "Project & Methodology", ":material/menu_book:"),
    ],
}
PAGE_FILES = [f for group in PAGES.values() for f, _, _ in group]


def url_path(filename: str) -> str:
    """``2_Dataset_Explorer.py`` -> ``dataset-explorer``."""
    return filename.split("_", 1)[1].removesuffix(".py").replace("_", "-").lower()


def run_app(default_page: str = PAGE_FILES[0]) -> None:
    st.set_page_config(page_title="Civil Aviation Analytics & Forecasting", page_icon="✈️", layout="wide",
                       initial_sidebar_state="expanded")
    groups = {
        name: [st.Page(ROOT / "app_pages" / f, title=title, icon=icon, default=(f == default_page),
                       url_path=None if f == default_page else url_path(f))
               for f, title, icon in items]
        for name, items in PAGES.items()
    }
    state.init_state()
    bundle = state.get_bundle()
    if bundle is not None:
        state.sanitize_filters(bundle)
    ui.inject_css()
    navigation = st.navigation([p for pages in groups.values() for p in pages], position="hidden")
    ui.render_sidebar(groups)
    navigation.run()
