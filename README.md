# Civil Aviation Analytics & Forecasting

**Multivariate Time Series Analysis for Forecasting Trends in the Civil Aviation Industry**

An interactive Streamlit dashboard that analyses quarterly international passenger and freight traffic
involving India, compares forecasting models with leakage-free rolling-origin evaluation, and produces an
eight-quarter passenger forecast with prediction intervals and downloadable reports.

## Key features

| Page | What it does |
| --- | --- |
| Executive Dashboard | KPI cards, trend/seasonality/correlation charts, actual vs predicted, model ranking, data-driven observations |
| Dataset Explorer | Local, uploaded or remote data; schema detection; data-quality report; filtered tables and CSV downloads |
| Exploratory Analysis | Passenger and freight trends, QoQ/YoY growth, annual totals, seasonality, statistics, correlation, decomposition, country breakdown |
| Time-Series Diagnostics | ADF tests (levels and differences), ACF/PACF, seasonal sub-series, Ljung-Box overview |
| Forecasting Laboratory | Seasonal Naive, SARIMAX, SARIMAX + exogenous regressors and VAR, with configurable parameters and suitability checks |
| Model Evaluation | Expanding-window one-step rolling-origin comparison (MAE, RMSE, MAPE, sMAPE), conditional vs operational exogenous modes, SARIMAX screening |
| Future Forecast | Forecast chart and table with interval widths, generated interpretation, validation checks, CSV/JSON/PNG/PDF downloads |
| Residual Analysis | In-sample residuals and, separately, rolling forecast errors: series, histogram, Q-Q, ACF, Ljung-Box, normality tests |
| Reports & Downloads | Markdown, PDF and JSON reports built from live results; ZIP of all outputs; library of the notebook's output files |
| Project & Methodology | Methodology, model differences, limitations and references |

## Technology stack

Python, Streamlit, Plotly, pandas, NumPy, SciPy, statsmodels, Matplotlib (static report charts),
ReportLab (PDF) and pytest.

## Dataset

Source: [Vonter/india-aviation-traffic](https://github.com/Vonter/india-aviation-traffic), file
`aggregated/international/country.csv`. Columns: `Year`, `Quarter`, `Country`, `PaxToIndia`, `PaxFromIndia`,
`FreightToIndia`, `FreightFromIndia`. Coverage is read from the data (currently 2015 Q1 – 2026 Q2,
46 quarters, 2,544 country records). The main target is **PaxToIndia** (passengers arriving in India).
The source does not document freight units, so freight is reported "in source units".

Data handling (all reported on the Dataset Explorer page):

* two-digit years `15`–`99` are read as 2015–2099;
* quarters must be 1–4; dates are quarter starts;
* non-numeric values become missing and are counted; negative values and duplicate keys are excluded and listed;
* country spelling variants that differ only by case, spaces or a trailing `*` (e.g. `UNITED ARAB EMIRATES*`)
  are merged when they never report the same quarter;
* records are summed once per quarter; country filters are applied before aggregation;
* the latest quarter is checked for completeness (calendar end, monthly coverage in `carrier.csv`, number of
  reporting countries, level against the same quarter a year earlier).

## Directory structure

```text
india-aviation-traffic-main/
├── app.py                       # entry point (streamlit run app.py)
├── requirements.txt
├── pytest.ini
├── .streamlit/config.toml       # light theme + navy sidebar
├── config/settings.py           # paths, schema, colours, model defaults
├── src/
│   ├── shell.py                 # page registry, sidebar, navigation
│   ├── state.py                 # session state, active dataset, cached model runs
│   ├── data_loader.py           # local / upload / remote loading
│   ├── validation.py            # schema detection and quality checks
│   ├── preprocessing.py         # cleaning, quarterly aggregation, filters
│   ├── eda.py                   # statistics, growth, decomposition, insights
│   ├── diagnostics.py           # ADF, ACF/PACF, Ljung-Box, residual tests
│   ├── forecasting.py           # Seasonal Naive, SARIMAX, VAR
│   ├── evaluation.py            # metrics and rolling-origin evaluation
│   ├── visualization.py         # shared Plotly theme and chart builders
│   ├── reporting.py             # Markdown / JSON / PDF / ZIP and static charts
│   ├── report_context.py        # gathers current results for reports
│   ├── artifacts.py             # read-only registry of notebook outputs
│   ├── ui.py                    # CSS, headers, KPI cards, tables, sidebar
│   └── utils.py
├── app_pages/                   # the ten dashboard pages
├── tests/                       # unit and integration tests
├── data/README.md
├── aggregated/                  # source data (unchanged)
├── notebooks/civil_aviation_forecasting.ipynb
├── outputs/                     # notebook outputs (unchanged); dashboard writes to outputs/dashboard_exports/
└── backup/notebooks/            # copy of the notebook before the E: → D: path change
```

Pages live in `app_pages/` rather than `pages/`: Streamlit treats a folder named `pages/` as its older
automatic multipage mode, which conflicts with the custom navigation used here.

## Installation (Windows)

Command Prompt:

```bat
cd /d D:\india-aviation-traffic-main
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

PowerShell: activate with `.venv\Scripts\Activate.ps1` (you may need
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once).

With Anaconda you can skip the virtual environment and run
`C:\Users\<you>\anaconda3\python.exe -m pip install -r requirements.txt`.

macOS / Linux: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.

## Launch

```bat
streamlit run app.py
```

or `python -m streamlit run app.py`. The browser opens at <http://localhost:8501>.

### Configuring paths on another machine

Paths are relative to the project folder by default. Override them with environment variables:

| Variable | Default |
| --- | --- |
| `AVIATION_PROJECT_DIR` | folder containing `app.py` |
| `AVIATION_DATA_DIR` | `aggregated/international` |
| `AVIATION_OUTPUT_DIR` | `outputs` |

Example (Command Prompt): `set AVIATION_DATA_DIR=E:\data\aviation` then `streamlit run app.py`.

## Using the dashboard

* **Upload a dataset** – Dataset Explorer → *Uploaded CSV* → choose a file → *Validate and use this file*.
  Invalid files are rejected with an explanation and the previous dataset stays active. Max 20 MB.
* **Refresh from GitHub** – Dataset Explorer → *Remote repository refresh*. Only happens on request; failures
  keep the last good dataset.
* **Filter** – the sidebar has the date range, countries, target variable, horizon, confidence level and
  seasonal period. All pages use the same filtered data.
* **Generate forecasts** – Forecasting Laboratory (any model and parameters) or Future Forecast (the official
  forecast; by default the model with the lowest rolling-origin error that does not need future observed values).
* **Compare models** – Model Evaluation: pick models, evaluation size and ranking metric, then *Run evaluation*.
  Results are also saved to `outputs/dashboard_exports/`.
* **Export reports** – Reports & Downloads → *Generate report package* → Markdown, PDF, JSON or a ZIP of everything.

## Notebook

`notebooks/civil_aviation_forecasting.ipynb` now reads data from `D:\india-aviation-traffic-main\...` (it
previously pointed at `E:\`). The original is kept in `backup/notebooks/`. Some files in `outputs/` carry
milestone prefixes (`review2_`, `review3_`, or a leading `_`); the dashboard shows and exports them under plain
names (e.g. `final_validation_metrics.csv`) without renaming anything on disk.

## Tests

```bat
python -m pytest
```

Covers validation (schema, years, quarters, duplicates, missing values, gaps, latest quarter, country variants),
preprocessing (no double counting, filters), forecasting (horizons, future dates, finite values, ordered bounds,
error messages), evaluation (metrics, zero-safe MAPE, shared dates, leakage guard, reproduction of the notebook's
rolling results) and integration tests that render every page through the app shell and generate reports.

## Troubleshooting

* *"No dataset is loaded"* – check that `aggregated/international/country.csv` exists or set `AVIATION_DATA_DIR`,
  then click *Reload dataset*.
* *Model could not be fitted* – the selection may be too short (narrow date range or few countries). Widen it or
  choose a simpler model; VAR needs at least five observations per coefficient.
* *Page shows old results* – change a setting or click *Reload dataset*; model runs are cached per configuration.
* *PDF button missing* – install ReportLab (`pip install reportlab`).

## Limitations

* About 46 quarterly observations: estimates, tests and intervals are uncertain.
* The 2020–2021 collapse and recovery is a structural break that affects every model.
* Rolling evaluation uses a small number of one-step forecasts.
* Intervals assume the model is correct; VAR intervals omit parameter uncertainty.
* Conditional exogenous evaluation uses observed future regressors and overstates real-time accuracy.

## References

* Hyndman, R. J., & Athanasopoulos, G. (2021). *Forecasting: Principles and Practice* (3rd ed.). OTexts.
* Box, G. E. P., Jenkins, G. M., Reinsel, G. C., & Ljung, G. M. (2015). *Time Series Analysis* (5th ed.). Wiley.
* Dickey, D. A., & Fuller, W. A. (1979). JASA 74(366), 427–431.
* Lütkepohl, H. (2005). *New Introduction to Multiple Time Series Analysis*. Springer.
* Seabold, S., & Perktold, J. (2010). statsmodels. Proc. 9th Python in Science Conference.
* Vonter. india-aviation-traffic. https://github.com/Vonter/india-aviation-traffic
