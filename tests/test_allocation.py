import numpy as np
import pandas as pd
import pytest

from conftest import make_wards
from config import RESOURCES
from resource_allocation import (allocate_crews, allocate_supply, available_stock, check_allocation_invariants,
                                 priority_scores, run_allocation)


def test_full_stock_meets_all_demand(toy_wards):
    t, s, c = run_allocation(toy_wards, stock_pct=100, total_crews=100)
    for r in RESOURCES:
        assert (t[f"{r}_allocated"] == t[f"{r}_required"]).all()
        assert (t[f"{r}_deficit"] == 0).all()
    assert not t["critical_deficit"].any()
    check_allocation_invariants(t, s, c)


@pytest.mark.parametrize("policy", ["weighted", "triage"])
def test_30_percent_stock(toy_wards, policy):
    t, s, c = run_allocation(toy_wards, stock_pct=30, total_crews=3, policy=policy)
    for r in RESOURCES:
        total = int(toy_wards[r].sum())
        stock = available_stock(total, 30)
        assert stock == int(np.floor(total * 0.3))
        assert t[f"{r}_allocated"].sum() == stock       # all available stock is used, none invented
        assert t[f"{r}_allocated"].sum() <= stock
        assert (t[f"{r}_allocated"] >= 0).all()
        assert (t[f"{r}_allocated"] <= t[f"{r}_required"]).all()
    check_allocation_invariants(t, s, c)


def test_deficit_warning_correct(toy_wards):
    t, _, _ = run_allocation(toy_wards, stock_pct=50, total_crews=0)
    expected = sum(t[f"{r}_required"] - t[f"{r}_allocated"] for r in RESOURCES) > 0
    assert (t["critical_deficit"] == expected).all()
    assert (t.loc[t["critical_deficit"], "alert"] == "CRITICAL SUPPLY DEFICIT").all()
    t100, _, _ = run_allocation(toy_wards, stock_pct=100, total_crews=0)
    assert (t100["alert"] == "Fully supplied").all()


def test_risk_and_density_prioritisation(toy_wards):
    p = priority_scores(toy_wards).set_index("ward_id")
    # same risk, higher density ranks first
    assert p.loc["A1", "priority"] > p.loc["A2", "priority"]
    # same density, higher risk ranks first
    assert p.loc["A1", "priority"] > p.loc["A3", "priority"]
    t, _, _ = run_allocation(toy_wards, stock_pct=40, policy="weighted")
    fill = t.set_index("ward_id")["saline_bags_needed_fill_pct"]
    assert fill["A1"] >= fill["A2"] >= fill["A3"]
    tri, _, _ = run_allocation(toy_wards, stock_pct=40, policy="triage")
    tri = tri.set_index("ward_id")
    assert tri.loc["A1", "saline_bags_needed_deficit"] == 0           # top ward fully served first
    assert tri.loc["A3", "saline_bags_needed_allocated"] == 0


@pytest.mark.parametrize("pct", [30, 37, 50, 63, 81, 99, 100])
def test_never_exceeds_stock_on_real_forecast(system, pct):
    from pipeline import run_plan
    r = run_plan(system, "2024-08-12", "4w", pct, 25)
    check_allocation_invariants(r["plan"], r["supply_summary"], r["crews"])


def test_deterministic(toy_wards):
    a = run_allocation(toy_wards, 45, 4)[0]
    b = run_allocation(toy_wards.sample(frac=1, random_state=3), 45, 4)[0]
    pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True))


def test_crews_never_exceed_available(toy_wards):
    for total in (0, 1, 2, 5, 100):
        t, s, c = run_allocation(toy_wards, 100, total)
        assert t["crews_assigned"].sum() <= total
        assert (t["crews_assigned"] <= t["crews_needed"]).all()
        assert c["assigned"] + c["idle"] == total


def test_crews_round_robin_spreads_coverage():
    got = allocate_crews([3, 3, 1, 0], 3)
    assert list(got) == [1, 1, 1, 0]


def test_zero_available_crews(toy_wards):
    t, _, c = run_allocation(toy_wards, 100, 0)
    assert t["crews_assigned"].sum() == 0 and c["shortfall"] == t["crews_needed"].sum()


def test_zero_demand():
    w = make_wards([("A", "A1", 40000, 0.0, "Low", 0, 0, 0), ("A", "A2", 50000, 0.0, "Low", 0, 0, 0)])
    t, s, c = run_allocation(w, 30, 10)
    assert (s["required"] == 0).all() and (s["allocated"] == 0).all()
    assert not t["critical_deficit"].any()
    assert c["assigned"] == 0


def test_empty_selection():
    w = make_wards([])
    t, s, c = run_allocation(w, 50, 5)
    assert t.empty and c["assigned"] == 0


def test_malformed_inputs(toy_wards):
    with pytest.raises(ValueError):
        available_stock(100, 130)
    with pytest.raises(ValueError):
        allocate_supply([5, -1], [1, 1], 3)
    with pytest.raises(ValueError):
        allocate_supply([5, 1], [1, 1], 3, policy="random")
    with pytest.raises(ValueError):
        allocate_crews([1, 2], -1)
    bad = toy_wards.copy()
    bad.loc[0, "risk"] = "Extreme"
    with pytest.raises(ValueError):
        run_allocation(bad, 50, 1)
    with pytest.raises(ValueError):
        priority_scores(toy_wards, weights={"risk": 0, "density": 0})
