import streamlit as st

from config import settings
from src import reporting, state, ui
from src.utils import quarter_label

ui.page_header("Project & Methodology", reporting.TITLE, eyebrow="About the project")
ctx = state.get_context()
if ctx is not None:
    q = ctx.bundle.quarterly
    st.info(f"Current dataset: {ctx.bundle.filename} · {len(q)} quarters ({quarter_label(q.index.min())} – "
            f"{quarter_label(q.index.max())})" + (f" · {len(ctx.bundle.countries)} countries" if ctx.bundle.has_country else ""))

ui.section("Project aim")
st.markdown(
    "The project studies international passenger and freight traffic between India and other countries. It "
    "describes historical patterns, tests their statistical properties, compares forecasting models with a fair, "
    "time-ordered evaluation and produces an eight-quarter forecast of **passengers arriving in India "
    "(PaxToIndia)** with explicit uncertainty. PaxFromIndia, FreightToIndia and FreightFromIndia support the "
    "exploratory and multivariate analysis.")

ui.section("Methodology")
steps = {
    "1 · Data collection": f"Country-level quarterly records from the DGCA-based repository "
                           f"[{settings.REMOTE_REPO_URL}]({settings.REMOTE_REPO_URL}) (`aggregated/international/country.csv`).",
    "2 · Data cleaning": "Schema detection, two-digit year conversion (15 → 2015), quarter validation, numeric checks, "
                         "negative-value and duplicate detection. Excluded rows are listed with a reason; nothing is "
                         "removed silently.",
    "3 · Quarterly aggregation": "Country records are summed once per quarter on a regular quarter-start index; "
                                 "country filters are applied before aggregation to avoid double counting. Gaps stay visible.",
    "4 · Exploratory analysis": "Trends, quarter-over-quarter and year-over-year growth (flagging small bases), annual "
                                "totals, seasonal profiles, distributions and correlations.",
    "5 · Stationarity testing": "Augmented Dickey-Fuller tests on levels and differences. H0 is a unit root; failing "
                                "to reject is not proof of non-stationarity.",
    "6 · Seasonal decomposition": "Classical additive or multiplicative decomposition with period 4, plus ACF/PACF "
                                  "and seasonal sub-series plots.",
    "7 · Forecasting models": "Seasonal Naive baseline, SARIMAX (optionally with exogenous traffic regressors) and a "
                              "VAR on differenced series.",
    "8 · Rolling-origin validation": "Expanding window, one step ahead: fit on quarters before t, forecast t, add t, "
                                     "repeat. Every model is scored on the same quarters and training data never "
                                     "include the forecast quarter.",
    "9 · Error metrics": "MAE (average absolute error), RMSE (penalises large errors), MAPE (percentage error, zero "
                         "actuals excluded) and sMAPE (symmetric percentage error).",
    "10 · Forecast uncertainty": "Prediction intervals from each model's error variance, widening with the horizon. "
                                 "They are conditional on the model being adequate and are not guarantees.",
}
for title, text in steps.items():
    with st.expander(title, expanded=False):
        st.markdown(text)

ui.section("How the models differ")
c1, c2, c3 = st.columns(3)
with c1, st.container(border=True):
    st.markdown("#### Seasonal Naive")
    st.markdown("Repeats the value from the same quarter one year earlier. No parameters are estimated, so it is "
                "hard to overfit. It is the **benchmark**: a complex model is only useful if it beats it.")
with c2, st.container(border=True):
    st.markdown("#### SARIMAX")
    st.markdown("Seasonal ARIMA with optional eXogenous regressors. It combines autoregressive (p, P), differencing "
                "(d, D) and moving-average (q, Q) terms at lag 1 and the seasonal lag. The notebook's starting "
                "point is (1,1,1)(1,1,0,4).")
with c3, st.container(border=True):
    st.markdown("#### VAR")
    st.markdown("Vector autoregression: each series is regressed on lags of all series, capturing joint dynamics of "
                "passengers and freight. It needs stationary inputs (here differences or log differences) and many "
                "observations per coefficient, so the lag order is capped on this short sample.")

ui.section("Why a baseline matters")
st.markdown(
    "Quarterly aviation traffic is strongly seasonal, so 'same quarter last year' is already a good forecast. "
    "Reporting a model's error without a baseline can make an average model look impressive. Comparing against "
    "Seasonal Naive on identical evaluation quarters shows how much the extra complexity actually adds.")

ui.section("Exogenous variables: conditional vs operational")
st.markdown(
    "- **Conditional evaluation** feeds SARIMAX the *observed* PaxFromIndia and freight values of the quarter being "
    "forecast. It answers: *how accurate would the model be if those values were known?*\n"
    "- **Operational evaluation** uses only information available at the forecast origin, projecting each regressor "
    "with Seasonal Naive. It answers: *how accurate is the model in real use?*\n\n"
    "Only the operational variant is used for genuine future forecasts.")

ui.section("Limitations")
for line in reporting.LIMITATIONS:
    st.markdown(f"- {line}")

ui.section("References")
for i, ref in enumerate(reporting.REFERENCES, 1):
    st.markdown(f"{i}. {ref}")

ui.section("Configuration")
st.markdown(
    f"- Project folder: `{settings.PROJECT_ROOT}`\n- Data folder: `{settings.DATA_DIR}` (override with "
    f"`AVIATION_DATA_DIR`)\n- Notebook outputs: `{settings.OUTPUT_DIR}` (override with `AVIATION_OUTPUT_DIR`)\n"
    f"- Dashboard exports: `{settings.EXPORT_DIR}`")
