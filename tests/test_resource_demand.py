
"""Unit tests for resource-demand estimation (src/resource_demand.py).

Checks that per-case rates are fitted correctly, that demand is rounded the documented way (half up), that
negative forecasts never create demand, and that the real dataset's resource columns are a deterministic
function of cases (the reason no separate ML model is used for supplies).
"""
import numpy as np
import pandas as pd
import pytest

from config import RESOURCES
from resource_demand import (add_demand_columns, demand_from_cases, evaluate_rates, fit_rates, mapping_table,
                             round_half_up)

TRUE_RATES = {"saline_bags_needed": 2.4, "diagnostic_kits_needed": 1.15, "hospital_beds_required": 0.3}


def toy_frame(cases):
    df = pd.DataFrame({"dengue_cases": cases})
    for r in RESOURCES:
        df[r] = np.floor(np.asarray(cases, dtype=float) * TRUE_RATES[r] + 0.5).astype(int)
    return df


def test_fit_rates_recovers_per_case_rates():
    df = toy_frame(list(range(0, 40)) * 3)
    rates = fit_rates(df)
    for r in RESOURCES:
        assert rates[r] == pytest.approx(TRUE_RATES[r], abs=0.02)


def test_fit_rates_rejects_data_without_cases():
    with pytest.raises(ValueError):
        fit_rates(toy_frame([0, 0, 0]))


def test_round_half_up():
    assert list(round_half_up([0.49, 0.5, 1.5, 2.5, 3.2])) == [0, 1, 2, 3, 3]


def test_demand_from_cases_clips_negative_forecasts():
    d = demand_from_cases([-3.0, 0.0, 10.0], TRUE_RATES)
    assert list(d["saline_bags_needed"]) == [0, 0, 24]
    assert list(d["hospital_beds_required"]) == [0, 0, 3]
    for r in RESOURCES:
        assert (d[r] >= 0).all()


def test_evaluate_rates_exact_on_matching_data():
    df = toy_frame(list(range(0, 30)))
    ev = evaluate_rates(df, TRUE_RATES)
    for r in RESOURCES:
        assert ev[r]["exact_match"] == 1.0 and ev[r]["mae"] == 0.0


def test_add_demand_columns_adds_one_column_per_resource():
    frame = pd.DataFrame({"ward_id": ["A1", "A2"], "predicted_cases": [5.0, 12.4]})
    out = add_demand_columns(frame, TRUE_RATES)
    assert set(RESOURCES) <= set(out.columns)
    assert list(out["diagnostic_kits_needed"]) == [6, 14]
    assert "saline_bags_needed" not in frame.columns          # input left unchanged


def test_real_dataset_resources_are_deterministic_in_cases(system):
    table, deterministic = mapping_table(system["raw"])
    assert deterministic                                     # each case count maps to exactly one value
    assert (table.loc[table["dengue_cases"] == 0, list(RESOURCES)] == 0).all().all()


def test_saved_rates_come_from_training_years(system):
    from data_processing import load_raw
    raw = load_raw()
    train = raw[pd.to_datetime(raw["date"]) < pd.Timestamp(system["meta"]["split_date"])]
    refit = fit_rates(train)
    for r in RESOURCES:
        assert system["meta"]["resource_rates"][r] == pytest.approx(refit[r], abs=1e-4)
