"""Central configuration for the Civil Aviation Analytics & Forecasting dashboard.

All paths are resolved with ``pathlib`` relative to the project folder, and every
location can be overridden with an environment variable so the app runs on any
machine (Windows, macOS, Linux or Streamlit Community Cloud):

* ``AVIATION_PROJECT_DIR`` - project root (default: folder containing ``app.py``)
* ``AVIATION_DATA_DIR``    - folder holding ``country.csv`` (default: ``aggregated/international``)
* ``AVIATION_OUTPUT_DIR``  - notebook outputs folder (default: ``outputs``)
"""

from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- paths
PROJECT_ROOT = Path(
    os.environ.get("AVIATION_PROJECT_DIR", Path(__file__).resolve().parents[1])
).resolve()
DATA_DIR = Path(
    os.environ.get("AVIATION_DATA_DIR", PROJECT_ROOT / "aggregated" / "international")
).resolve()
OUTPUT_DIR = Path(os.environ.get("AVIATION_OUTPUT_DIR", PROJECT_ROOT / "outputs")).resolve()

# New files written by the dashboard go to a sub-folder so the notebook outputs
# are never overwritten.
EXPORT_DIR = OUTPUT_DIR / "dashboard_exports"

COUNTRY_CSV = DATA_DIR / "country.csv"
CARRIER_MONTHLY_CSV = DATA_DIR / "carrier.csv"  # optional: used for month-coverage check
QUARTERLY_CSV = OUTPUT_DIR / "quarterly_aviation_traffic.csv"

REMOTE_REPO_URL = "https://github.com/Vonter/india-aviation-traffic"
REMOTE_COUNTRY_URL = (
    "https://raw.githubusercontent.com/Vonter/india-aviation-traffic/main/"
    "aggregated/international/country.csv"
)
REMOTE_TIMEOUT_SECONDS = 20

MAX_UPLOAD_MB = 20

# --------------------------------------------------------------------------- schema
TRAFFIC_COLUMNS = ["PaxToIndia", "PaxFromIndia", "FreightToIndia", "FreightFromIndia"]
PASSENGER_COLUMNS = ["PaxToIndia", "PaxFromIndia"]
FREIGHT_COLUMNS = ["FreightToIndia", "FreightFromIndia"]
TARGET = "PaxToIndia"
EXOG_COLUMNS = ["PaxFromIndia", "FreightToIndia", "FreightFromIndia"]

LABELS = {
    "Date": "Quarter",
    "Year": "Year",
    "Quarter": "Quarter No.",
    "Country": "Country",
    "PaxToIndia": "Passengers to India",
    "PaxFromIndia": "Passengers from India",
    "FreightToIndia": "Freight to India",
    "FreightFromIndia": "Freight from India",
}
SERIES_TITLES = {
    "PaxToIndia": "Passenger Traffic to India",
    "PaxFromIndia": "Passenger Traffic from India",
    "FreightToIndia": "Freight Traffic to India",
    "FreightFromIndia": "Freight Traffic from India",
}
# The source repository does not document a freight unit, so none is invented.
UNITS = {
    "PaxToIndia": "passengers",
    "PaxFromIndia": "passengers",
    "FreightToIndia": "freight, source units",
    "FreightFromIndia": "freight, source units",
}

# --------------------------------------------------------------------------- model defaults
DEFAULT_HORIZON = 8
DEFAULT_SEASONAL_PERIOD = 4
DEFAULT_ORDER = (1, 1, 1)
DEFAULT_SEASONAL_ORDER = (1, 1, 0)  # seasonal period appended at run time
DEFAULT_CI_LEVEL = 95
DEFAULT_TEST_SIZE = 12

# --------------------------------------------------------------------------- design tokens
COLORS = {
    "text": "#172B4D",
    "text_secondary": "#52677F",
    "text_muted": "#62748A",
    "background": "#F4F7FB",
    "card": "#FFFFFF",
    "border": "#DCE5EF",
    "grid": "#E8EEF5",
    "primary": "#2563EB",
    "navy": "#0B1F33",
    "sky": "#38BDF8",
    "positive": "#0D9488",
    "warning": "#F59E0B",
    "negative": "#DC2626",
}
SERIES_COLORS = {
    "PaxToIndia": "#2563EB",
    "PaxFromIndia": "#0D9488",
    "FreightToIndia": "#F59E0B",
    "FreightFromIndia": "#7C3AED",
}
MODEL_COLORS = {
    "Actual": "#172B4D",
    "SARIMAX": "#2563EB",
    "Seasonal Naive": "#0D9488",
    "VAR": "#F59E0B",
    "SARIMAX + exog (conditional)": "#7C3AED",
    "SARIMAX + exog (operational)": "#DB2777",
}
QUARTER_COLORS = ["#2563EB", "#0D9488", "#F59E0B", "#7C3AED"]

# --------------------------------------------------------------------------- notebook artifacts
# Some files in outputs/ carry milestone prefixes ("review2_", "review3_") or a bare
# leading underscore. The dashboard never renames them on disk; it shows and
# exports them under these plain names instead.
ARTIFACT_ALIASES = {
    "review2_model_comparison.csv": "rolling_three_model_comparison.csv",
    "_model_comparison.csv": "rolling_three_model_comparison.csv",
    "review2_project_summary.csv": "project_summary.csv",
    "_project_summary.csv": "project_summary.csv",
    "review2_residual_diagnostics.png": "rolling_residual_diagnostics.png",
    "_residual_diagnostics.png": "rolling_residual_diagnostics.png",
    "review2_three_model_forecast_comparison.png": "three_model_forecast_comparison.png",
    "_three_model_forecast_comparison.png": "three_model_forecast_comparison.png",
}

ARTIFACT_DESCRIPTIONS = {
    "quarterly_aviation_traffic.csv": "Quarterly totals aggregated from country.csv",
    "adf_stationarity_results.csv": "Augmented Dickey-Fuller tests (levels and first differences)",
    "rolling_origin_forecasts.csv": "One-step rolling-origin forecasts (SARIMAX, Seasonal Naive)",
    "rolling_origin_model_metrics.csv": "Rolling-origin error metrics",
    "var_rolling_origin_forecasts.csv": "One-step rolling-origin VAR forecasts",
    "rolling_three_model_comparison.csv": "Three-model rolling-origin comparison",
    "final_validation_metrics.csv": "Final validation metrics (tuned SARIMAX vs baseline)",
    "final_validation_forecasts.csv": "Final validation forecasts",
    "sarimax_configuration_comparison.csv": "SARIMAX order screening on the rolling window",
    "final_8_quarter_forecast.csv": "Final 8-quarter passenger forecast",
    "final_passenger_forecast_8_quarters.csv": "8-quarter passenger forecast (earlier run)",
    "log_sarimax_passenger_forecast.csv": "Log-SARIMAX passenger forecast",
    "future_passenger_forecast.csv": "Four-quarter forecast from the 80/20 notebook split",
    "model_comparison.csv": "Hold-out comparison from the 80/20 notebook split",
    "final_model_comparison.csv": "Four-quarter fair comparison from the notebook",
    "final_model_ranking.csv": "Model ranking by MAE",
    "final_forecast_summary.csv": "Forecast summary",
    "final_data_quality_audit.csv": "Output file audit",
    "project_summary.csv": "Project summary",
}
