import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from config import settings  # noqa: E402
from src import data_loader  # noqa: E402


def make_country_frame(years=(15, 16, 17, 18, 19), countries=("A", "B")) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    rows = []
    for y in years:
        for q in range(1, 5):
            for c in countries:
                base = 1000 * (1 + 0.1 * q) * (1 + 0.05 * (y - years[0]))
                rows.append({"Year": y, "Quarter": q, "Country": c,
                             "PaxToIndia": round(base + rng.normal(0, 20)), "PaxFromIndia": round(base * 1.05),
                             "FreightToIndia": base / 10, "FreightFromIndia": base / 8})
    return pd.DataFrame(rows)


@pytest.fixture
def country_frame() -> pd.DataFrame:
    return make_country_frame()


@pytest.fixture(scope="session")
def real_bundle():
    if not settings.COUNTRY_CSV.exists():
        pytest.skip("country.csv not available")
    return data_loader.load_country_source()


@pytest.fixture(scope="session")
def real_quarterly(real_bundle) -> pd.DataFrame:
    return real_bundle.quarterly


@pytest.fixture
def synthetic_quarterly() -> pd.DataFrame:
    idx = pd.date_range("2010-01-01", periods=48, freq="QS-JAN", name="Date")
    t = np.arange(48)
    rng = np.random.default_rng(1)
    season = np.tile([0.95, 1.0, 0.98, 1.08], 12)
    base = (1e6 + 2e4 * t) * season
    return pd.DataFrame({
        "PaxToIndia": base * (1 + rng.normal(0, 0.01, 48)),
        "PaxFromIndia": base * 1.03 * (1 + rng.normal(0, 0.01, 48)),
        "FreightToIndia": base / 50 * (1 + rng.normal(0, 0.02, 48)),
        "FreightFromIndia": base / 30 * (1 + rng.normal(0, 0.02, 48)),
    }, index=idx)
