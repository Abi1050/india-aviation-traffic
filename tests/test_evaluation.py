import numpy as np
import pandas as pd
import pytest

from src import evaluation as ev, forecasting as fc


def test_mae_rmse_known_values():
    a, p = [10, 20, 30], [12, 18, 33]
    assert ev.mae(a, p) == pytest.approx(7 / 3)
    assert ev.rmse(a, p) == pytest.approx(np.sqrt((4 + 4 + 9) / 3))


def test_mape_excludes_zero_actuals():
    value, n = ev.mape([0, 100, 200], [5, 110, 180])
    assert n == 2
    assert value == pytest.approx((0.10 + 0.10) / 2 * 100)
    value, n = ev.mape([0, 0], [1, 2])
    assert n == 0 and np.isnan(value)


def test_smape_and_bias():
    m = ev.compute_metrics([100, 200], [110, 190])
    assert m["Bias (mean error)"] == pytest.approx(0)
    assert m["sMAPE (%)"] == pytest.approx(np.mean([20 / 210, 20 / 390]) * 100)


def test_metric_length_mismatch():
    with pytest.raises(ValueError):
        ev.mae([1, 2], [1])


def test_rolling_origin_shared_dates_and_no_leakage(synthetic_quarterly, monkeypatch):
    seen = []
    original = ev._one_step

    def spy(model, train, next_row, *args, **kwargs):
        # The training window must end strictly before the quarter being forecast.
        assert train.index.max() < next_row.index[0]
        assert next_row.index[0] not in train.index
        seen.append((model, train.index.max(), next_row.index[0]))
        return original(model, train, next_row, *args, **kwargs)

    monkeypatch.setattr(ev, "_one_step", spy)
    models = [fc.NAIVE, fc.SARIMAX, fc.VAR_MODEL]
    res = ev.rolling_origin(synthetic_quarterly, "PaxToIndia", models, 8, 4, fc.SarimaxConfig(), fc.VarConfig())
    assert res["n_common"] == 8
    assert set(res["metrics"]["N"]) == {8}
    dates = {m: sorted(d for mm, _, d in seen if mm == m) for m in models}
    assert dates[fc.NAIVE] == dates[fc.SARIMAX] == dates[fc.VAR_MODEL]
    assert (res["forecasts"]["Train end"] < res["forecasts"].index).all()
    sizes = res["forecasts"]["Train size"].tolist()
    assert sizes == list(range(40, 48))


def test_conditional_vs_operational_exog_differ(synthetic_quarterly):
    res = ev.rolling_origin(synthetic_quarterly, "PaxToIndia", [fc.EXOG_CONDITIONAL, fc.EXOG_OPERATIONAL], 4, 4,
                            fc.SarimaxConfig(), fc.VarConfig())
    f = res["forecasts"]
    assert not np.allclose(f[fc.EXOG_CONDITIONAL], f[fc.EXOG_OPERATIONAL])


def test_insufficient_training_window(synthetic_quarterly):
    with pytest.raises(ValueError, match="training window"):
        ev.rolling_origin(synthetic_quarterly.iloc[:26], "PaxToIndia", [fc.VAR_MODEL], 6, 4, fc.SarimaxConfig(),
                          fc.VarConfig())


def test_best_model():
    m = pd.DataFrame({"Model": ["A", "B"], "MAE": [3.0, 2.0], "RMSE": [1.0, 5.0]})
    assert ev.best_model(m, "MAE") == "B"
    assert ev.best_model(m, "RMSE") == "A"
    assert ev.best_model(m, "MAE", ["A"]) == "A"


def test_reproduces_notebook_rolling_metrics(real_quarterly):
    """The notebook's rolling-origin results (outputs/rolling_three_model_comparison) are recovered exactly."""
    res = ev.rolling_origin(real_quarterly, "PaxToIndia", [fc.NAIVE, fc.SARIMAX, fc.VAR_MODEL], 12, 4,
                            fc.SarimaxConfig(), fc.VarConfig())
    mae = res["metrics"].set_index("Model")["MAE"]
    assert res["period_label"] == "2023 Q3 – 2026 Q2"
    assert mae[fc.SARIMAX] == pytest.approx(356699.2299, rel=1e-6)
    assert mae[fc.NAIVE] == pytest.approx(920134.8333, rel=1e-6)
    assert mae[fc.VAR_MODEL] == pytest.approx(880632.1939, rel=1e-6)
