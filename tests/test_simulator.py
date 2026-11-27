import math

import pandas as pd
import pytest

from intervention_simulator import default_params, effect, optimal_deployment, simulate

RATES = {"saline_bags_needed": 2.4, "diagnostic_kits_needed": 1.2, "hospital_beds_required": 0.3}


@pytest.fixture
def fc():
    return pd.DataFrame({"city": ["A", "A", "B"], "ward_id": ["A1", "A2", "B1"], "risk": ["Critical", "Low", "High"],
                         "cases_2w": [20.0, 1.0, 10.0], "cases_4w": [30.0, 2.0, 12.0]})


def test_zero_intervention_prevents_nothing(fc):
    t, tot = simulate(fc, {}, 5, RATES, "4w")
    assert tot["cases_prevented"] == 0 and (t["prevented_2w"] == 0).all() and (t["prevented_4w"] == 0).all()
    assert tot["simulated_cases"] == tot["baseline_cases"]
    assert float(effect(0)) == 0.0


def test_cases_prevented_per_crew(fc):
    p = default_params()
    t, tot = simulate(fc, {"A1": 2}, 5, RATES, "4w")
    expected = 30.0 * p["max_reduction"] * (1 - math.exp(-2 / p["saturation_crews"])) * p["timing"]["4w"]
    row = t.set_index("ward_id").loc["A1"]
    assert row["prevented_4w"] == pytest.approx(expected, abs=0.01)
    assert row["cases_prevented_per_crew"] == pytest.approx(expected / 2, abs=0.01)
    assert tot["cases_prevented_per_crew"] == pytest.approx(expected / 2, abs=0.01)
    assert row["beds_reduction"] == pytest.approx(expected * 0.3, abs=0.01)
    assert row["saline_reduction"] == pytest.approx(expected * 2.4, abs=0.01)
    # baseline and scenario both present; 2w effect smaller than 4w by the timing assumption
    assert row["simulated_4w"] < 30.0 and row["prevented_2w"] < row["prevented_4w"]


def test_teams_cannot_exceed_available(fc):
    with pytest.raises(ValueError):
        simulate(fc, {"A1": 3, "B1": 3}, 5, RATES)
    with pytest.raises(ValueError):
        simulate(fc, {"A1": -1}, 5, RATES)
    with pytest.raises(ValueError):
        simulate(fc, {"Z9": 1}, 5, RATES)
    plan = optimal_deployment(fc, 4, "4w")
    assert sum(plan.values()) <= 4


def test_zero_available_crews(fc):
    assert optimal_deployment(fc, 0) == {}
    t, tot = simulate(fc, {}, 0, RATES)
    assert tot["crews_assigned"] == 0 and tot["cases_prevented_per_crew"] == 0


def test_roi_ranking_and_determinism(fc):
    t1, _ = simulate(fc, {"A1": 1, "B1": 1, "A2": 1}, 3, RATES, "2w")
    assert list(t1["ward_id"]) == ["A1", "B1", "A2"]       # higher baseline -> more cases prevented per crew
    assert list(t1["roi_rank"]) == [1, 2, 3]
    t2, _ = simulate(fc.iloc[::-1], {"A2": 1, "B1": 1, "A1": 1}, 3, RATES, "2w")
    pd.testing.assert_frame_equal(t1, t2)


def test_optimal_deployment_beats_naive(fc):
    plan = optimal_deployment(fc, 3, "4w")
    best = simulate(fc, plan, 3, RATES, "4w")[1]["cases_prevented"]
    naive = simulate(fc, {"A2": 3}, 3, RATES, "4w")[1]["cases_prevented"]
    assert best >= naive


def test_invalid_params(fc):
    p = default_params()
    p["max_reduction"] = 1.5
    with pytest.raises(ValueError):
        simulate(fc, {}, 1, RATES, params=p)
