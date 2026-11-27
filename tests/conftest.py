import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture(scope="session")
def system():
    from pipeline import load_system
    return load_system()


def make_wards(rows):
    """rows: list of (city, ward_id, density, cases, risk, saline, kits, beds)."""
    return pd.DataFrame(rows, columns=["city", "ward_id", "population_density_sqkm", "predicted_cases", "risk",
                                       "saline_bags_needed", "diagnostic_kits_needed", "hospital_beds_required"])


@pytest.fixture
def toy_wards():
    return make_wards([
        ("A", "A1", 70000, 15.0, "Critical", 36, 17, 4),
        ("A", "A2", 20000, 15.0, "Critical", 36, 17, 4),
        ("A", "A3", 70000, 2.0, "Low", 5, 2, 1),
        ("B", "B1", 45000, 8.0, "Medium", 19, 9, 2),
        ("B", "B2", 30000, 11.0, "High", 26, 13, 3),
    ])
