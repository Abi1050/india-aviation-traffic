import io

import numpy as np
import pandas as pd
import pytest

from config import settings
from src import data_loader
from src.preprocessing import aggregate_quarterly, filter_quarterly, model_ready, prepare_dataset


def test_aggregation_sums_each_record_once(country_frame):
    bundle = prepare_dataset(country_frame, "test", "t.csv")
    assert len(bundle.quarterly) == 20
    for col in settings.TRAFFIC_COLUMNS:
        assert bundle.quarterly[col].sum() == pytest.approx(country_frame[col].sum())


def test_country_filter_applied_before_aggregation(country_frame):
    bundle = prepare_dataset(country_frame, "test", "t.csv")
    only_a = filter_quarterly(bundle, ["A"])
    expected = country_frame[country_frame["Country"] == "A"]["PaxToIndia"].sum()
    assert only_a["PaxToIndia"].sum() == pytest.approx(expected)
    both = filter_quarterly(bundle, ["A", "B"])
    assert both["PaxToIndia"].sum() == pytest.approx(country_frame["PaxToIndia"].sum())


def test_date_window_filter(country_frame):
    bundle = prepare_dataset(country_frame, "test", "t.csv")
    sub = filter_quarterly(bundle, None, pd.Timestamp("2016-04-01"), pd.Timestamp("2017-01-01"))
    assert sub.index.min() == pd.Timestamp("2016-04-01") and len(sub) == 4
    assert sub.index.freqstr.startswith("QS")


def test_quarterly_layout_loaded(country_frame):
    q = prepare_dataset(country_frame, "test", "t.csv").quarterly.reset_index()
    q["Date"] = q["Date"].dt.strftime("%Y-%m-%d")
    bundle = data_loader.load_upload(q.to_csv(index=False).encode(), "agg.csv")
    assert bundle.fmt == "quarterly" and not bundle.has_country
    assert len(bundle.quarterly) == 20


def test_mid_quarter_dates_are_aligned():
    df = pd.DataFrame({"Date": ["2020-02-15", "2020-05-01"], "PaxToIndia": [1, 2], "PaxFromIndia": [1, 2],
                       "FreightToIndia": [1, 2], "FreightFromIndia": [1, 2]})
    bundle = prepare_dataset(df, "test", "t.csv")
    assert list(bundle.quarterly.index) == [pd.Timestamp("2020-01-01"), pd.Timestamp("2020-04-01")]
    assert "Quarter alignment" in bundle.quality["Check"].values


def test_model_ready_reports_gaps():
    idx = pd.date_range("2020-01-01", periods=6, freq="QS-JAN")
    df = pd.DataFrame({"PaxToIndia": [1, 2, np.nan, 4, 5, 6]}, index=idx)
    problems = model_ready(df, ["PaxToIndia", "Missing"])
    assert any("2020 Q3" in p for p in problems) and any("Missing" in p for p in problems)


def test_real_data_matches_notebook_aggregate(real_quarterly):
    assert len(real_quarterly) == 46
    assert real_quarterly.index.min() == pd.Timestamp("2015-01-01")
    assert real_quarterly.index.max() == pd.Timestamp("2026-04-01")
    if settings.QUARTERLY_CSV.exists():
        saved = pd.read_csv(settings.QUARTERLY_CSV, parse_dates=["Date"]).set_index("Date")
        np.testing.assert_allclose(real_quarterly[settings.TRAFFIC_COLUMNS].to_numpy(),
                                   saved[settings.TRAFFIC_COLUMNS].to_numpy(), rtol=1e-9)


def test_empty_records_aggregate():
    empty = pd.DataFrame(columns=["Date", *settings.TRAFFIC_COLUMNS])
    assert aggregate_quarterly(empty).empty
