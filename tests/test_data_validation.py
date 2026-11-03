import numpy as np
import pandas as pd
import pytest

from src import data_loader
from src.preprocessing import prepare_dataset
from src.validation import (FORMAT_COUNTRY, FORMAT_QUARTERLY, FORMAT_YEAR_QUARTER, SchemaError, detect_format,
                            latest_quarter_assessment, normalise_years, validate_quarters)


def quality(bundle, check):
    return bundle.quality.set_index("Check").loc[check]


def test_required_columns_recognised(country_frame):
    assert detect_format(country_frame.columns) == FORMAT_COUNTRY
    assert detect_format(country_frame.drop(columns="Country").columns) == FORMAT_YEAR_QUARTER
    agg = pd.DataFrame(columns=["Date", "PaxToIndia", "PaxFromIndia", "FreightToIndia", "FreightFromIndia"])
    assert detect_format(agg.columns) == FORMAT_QUARTERLY


def test_missing_required_column_is_rejected(country_frame):
    with pytest.raises(SchemaError, match="FreightFromIndia"):
        detect_format(country_frame.drop(columns="FreightFromIndia").columns)
    with pytest.raises(SchemaError, match="date information"):
        detect_format(country_frame.drop(columns=["Year", "Quarter", "Country"]).columns)


def test_column_names_matched_case_insensitively(country_frame):
    df = country_frame.rename(columns={"PaxToIndia": " paxtoindia ", "Year": "YEAR"})
    bundle = prepare_dataset(df, "test", "t.csv")
    assert bundle.fmt == FORMAT_COUNTRY


def test_two_digit_years_converted():
    years, converted, invalid = normalise_years(pd.Series([15, 2016, 26, 150, "x"]))
    assert years.tolist()[:3] == [2015, 2016, 2026]
    assert converted == 2
    assert invalid.tolist() == [False, False, False, True, True]


def test_invalid_quarters_detected(country_frame):
    q, bad = validate_quarters(pd.Series([1, "Q2", 4, 5, 0, 2.5]))
    assert bad.tolist() == [False, False, False, True, True, True]
    df = country_frame.copy()
    df.loc[0, "Quarter"] = 5
    bundle = prepare_dataset(df, "test", "t.csv")
    assert quality(bundle, "Quarter values")["Status"] == "Fail"
    assert len(bundle.excluded) == 1 and bundle.excluded["Reason"].iloc[0] == "Invalid year or quarter"
    assert len(bundle.records) == len(df) - 1


def test_dates_are_chronological_quarter_starts(country_frame):
    bundle = prepare_dataset(country_frame.sample(frac=1, random_state=3), "test", "t.csv")
    idx = bundle.quarterly.index
    assert idx.is_monotonic_increasing
    assert (idx.month.isin([1, 4, 7, 10]) & (idx.day == 1)).all()
    assert idx.min() == pd.Timestamp("2015-01-01")


def test_duplicates_detected_and_not_double_counted(country_frame):
    df = pd.concat([country_frame, country_frame.iloc[[0]]], ignore_index=True)
    conflicting = country_frame.iloc[[1]].copy()
    conflicting["PaxToIndia"] += 999
    df = pd.concat([df, conflicting], ignore_index=True)
    bundle = prepare_dataset(df, "test", "t.csv")
    assert quality(bundle, "Duplicate rows")["Rows affected"] == 1
    assert quality(bundle, "Duplicate quarter-country keys")["Rows affected"] == 1
    assert len(bundle.records) == len(country_frame)
    assert bundle.quarterly["PaxToIndia"].sum() == pytest.approx(country_frame["PaxToIndia"].sum())


def test_missing_and_non_numeric_values_reported(country_frame):
    df = country_frame.astype({"PaxToIndia": object})
    df.loc[0, "PaxToIndia"] = "n/a"
    df.loc[1, "FreightToIndia"] = np.nan
    bundle = prepare_dataset(df, "test", "t.csv")
    assert quality(bundle, "Numeric values")["Rows affected"] == 1
    assert quality(bundle, "Missing values")["Rows affected"] == 2
    assert len(bundle.records) == len(df)  # kept, not dropped silently


def test_negative_values_excluded_with_reason(country_frame):
    df = country_frame.copy()
    df.loc[3, "PaxFromIndia"] = -10
    bundle = prepare_dataset(df, "test", "t.csv")
    assert bundle.excluded["Reason"].tolist() == ["Negative traffic value"]


def test_missing_quarter_reported(country_frame):
    df = country_frame[~((country_frame["Year"] == 17) & (country_frame["Quarter"] == 2))]
    bundle = prepare_dataset(df, "test", "t.csv")
    row = quality(bundle, "Quarter coverage")
    assert row["Status"] == "Warning" and "2017 Q2" in row["Details"]
    assert bundle.quarterly.loc["2017-04-01"].isna().all()


def test_latest_quarter_in_progress_flagged(country_frame):
    bundle = prepare_dataset(country_frame, "test", "t.csv")
    latest = latest_quarter_assessment(bundle.quarterly, bundle.records, today=pd.Timestamp("2019-11-15"))
    assert not latest["complete"]
    done = latest_quarter_assessment(bundle.quarterly, bundle.records, today=pd.Timestamp("2020-02-01"))
    assert done["complete"]


def test_upload_size_and_empty_rejected():
    with pytest.raises(data_loader.DataLoadError):
        data_loader.read_csv_bytes(b"   ")
    with pytest.raises(data_loader.DataLoadError, match="larger"):
        data_loader.read_csv_bytes(b"a,b\n" * 10, max_mb=0.00001)


def test_real_dataset_quality(real_bundle):
    assert real_bundle.fmt == FORMAT_COUNTRY
    assert real_bundle.excluded.empty
    assert len(real_bundle.countries) > 50
    assert real_bundle.latest["label"] == "2026 Q2"


def test_country_spelling_variants_harmonised(country_frame):
    df = country_frame.copy()
    early = (df["Country"] == "A") & (df["Year"] <= 16)
    df.loc[early, "Country"] = "A*"
    bundle = prepare_dataset(df, "test", "t.csv")
    assert bundle.countries == ["A", "B"]
    assert quality(bundle, "Country name variants")["Rows affected"] == int(early.sum())
    assert bundle.quarterly["PaxToIndia"].sum() == pytest.approx(df["PaxToIndia"].sum())


def test_overlapping_country_variants_kept_apart(country_frame):
    extra = country_frame[country_frame["Country"] == "A"].copy()
    extra["Country"] = "a "
    bundle = prepare_dataset(pd.concat([country_frame, extra]), "test", "t.csv")
    assert "Country name variants (overlapping)" in bundle.quality["Check"].values
    assert len(bundle.countries) == 3
