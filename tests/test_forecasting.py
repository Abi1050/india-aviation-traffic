import numpy as np
import pandas as pd
import pytest

from config import settings
from src import forecasting as fc

MODELS = [fc.NAIVE, fc.SARIMAX, fc.VAR_MODEL, fc.EXOG_OPERATIONAL]


def run(model, q, horizon=8):
    return fc.run_forecast(model, q, "PaxToIndia", horizon, 95, 4, fc.SarimaxConfig(), fc.VarConfig())


@pytest.mark.parametrize("bad", [0, -1, 2.5, True, 999])
def test_invalid_horizon_rejected(bad, synthetic_quarterly):
    with pytest.raises(fc.ForecastError):
        fc.seasonal_naive_forecast(synthetic_quarterly["PaxToIndia"], bad)


@pytest.mark.parametrize("model", MODELS)
def test_forecast_shape_dates_and_bounds(model, synthetic_quarterly):
    res = run(model, synthetic_quarterly, 6)
    f = res.forecast
    assert len(f) == 6
    assert f.index[0] == synthetic_quarterly.index[-1] + pd.offsets.QuarterBegin(startingMonth=1)
    assert f.index.min() > synthetic_quarterly.index.max()
    assert (f.index.to_series().diff().dropna().dt.days.between(89, 92)).all()
    assert np.isfinite(f.to_numpy()).all()
    assert ((f["Lower"] <= f["Forecast"]) & (f["Forecast"] <= f["Upper"])).all()
    checks = fc.validate_forecast(f, synthetic_quarterly.index, 6)
    assert checks.set_index("Check").loc["Forecast dates are consecutive quarters", "Passed"]


def test_seasonal_naive_repeats_last_season(synthetic_quarterly):
    s = synthetic_quarterly["PaxToIndia"]
    res = fc.seasonal_naive_forecast(s, 8)
    np.testing.assert_allclose(res.forecast["Forecast"].to_numpy(), np.tile(s.iloc[-4:].to_numpy(), 2))
    # intervals widen once per season
    width = res.forecast["Upper"] - res.forecast["Lower"]
    assert width.iloc[4] > width.iloc[3] and width.iloc[0] == pytest.approx(width.iloc[3])


def test_non_numeric_and_missing_inputs_give_clear_errors(synthetic_quarterly):
    s = synthetic_quarterly["PaxToIndia"].astype(object)
    s.iloc[3] = "abc"
    with pytest.raises(fc.ForecastError, match="not numeric"):
        fc.sarimax_forecast(s.rename("PaxToIndia"), 4, fc.SarimaxConfig())
    s2 = synthetic_quarterly["PaxToIndia"].copy()
    s2.iloc[5] = np.nan
    with pytest.raises(fc.ForecastError, match="missing"):
        fc.sarimax_forecast(s2, 4, fc.SarimaxConfig())


def test_too_short_series_fails_with_message(synthetic_quarterly):
    with pytest.raises(fc.ForecastError, match="at least"):
        fc.sarimax_forecast(synthetic_quarterly["PaxToIndia"].iloc[:10], 4, fc.SarimaxConfig())


def test_log_sarimax_keeps_bounds_positive(synthetic_quarterly):
    res = fc.sarimax_forecast(synthetic_quarterly["PaxToIndia"], 8, fc.SarimaxConfig(log=True))
    assert (res.forecast["Lower"] > 0).all()


def test_conditional_exog_cannot_forecast_future(synthetic_quarterly):
    with pytest.raises(fc.ForecastError, match="cannot"):
        run(fc.EXOG_CONDITIONAL, synthetic_quarterly)


def test_var_suitability_rejects_short_samples(synthetic_quarterly):
    short = fc.var_suitability(synthetic_quarterly.iloc[:12], fc.VarConfig())
    assert not short["ok"] and short["problems"]
    ok = fc.var_suitability(synthetic_quarterly, fc.VarConfig())
    assert ok["ok"] and ok["lag_cap"] >= 1


def test_var_requires_positive_values_for_logs(synthetic_quarterly):
    df = synthetic_quarterly.copy()
    df.iloc[4, 2] = 0
    res = fc.var_suitability(df, fc.VarConfig())
    assert not res["ok"] and "positive" in res["problems"][0]


def test_reproduces_notebook_sarimax_forecast(real_quarterly):
    res = run(fc.SARIMAX, real_quarterly)
    assert res.forecast.index[0] == pd.Timestamp("2026-07-01")
    saved = settings.OUTPUT_DIR / "final_passenger_forecast_8_quarters.csv"
    if saved.exists():
        ref = pd.read_csv(saved)
        np.testing.assert_allclose(res.forecast["Forecast"].to_numpy(), ref["Forecast_PaxToIndia"].to_numpy(), rtol=1e-4)
