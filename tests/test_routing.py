import pandas as pd
import pytest

from hospital_routing import check_routing_invariants, route_overflow


def _beds(rows):
    return pd.DataFrame(rows, columns=["city", "ward_id", "beds_demand"])


def _cap(rows):
    return pd.DataFrame(rows, columns=["ward_id", "bed_capacity"])


def test_routes_overflow_within_city():
    beds = _beds([("A", "A1", 9), ("A", "A2", 1), ("A", "A3", 2), ("B", "B1", 0)])
    cap = _cap([("A1", 5), ("A2", 4), ("A3", 4), ("B1", 20)])
    t, tr, city = route_overflow(beds, cap)
    assert tr["patients"].sum() == 4
    assert set(tr["to_ward"]) <= {"A2", "A3"}
    assert (tr["city"] == "A").all()
    a1 = t.set_index("ward_id").loc["A1"]
    assert a1["unresolved_deficit"] == 0 and a1["transferred_out"] == 4
    check_routing_invariants(t, tr)


def test_no_cross_city_transfer_even_with_spare_beds_elsewhere():
    beds = _beds([("A", "A1", 10), ("A", "A2", 5), ("B", "B1", 0)])
    cap = _cap([("A1", 5), ("A2", 5), ("B1", 50)])
    t, tr, city = route_overflow(beds, cap)
    assert tr.empty                                 # city A is full; B has beds but must not be used
    assert t.set_index("ward_id").loc["A1", "unresolved_deficit"] == 5
    check_routing_invariants(t, tr)


def test_receiving_capacity_never_exceeded_and_insufficient_capacity():
    beds = _beds([("A", "A1", 12), ("A", "A2", 8), ("A", "A3", 1), ("A", "A4", 0)])
    cap = _cap([("A1", 4), ("A2", 4), ("A3", 3), ("A4", 2)])
    t, tr, city = route_overflow(beds, cap)
    assert (t["beds_used_after"] <= t["bed_capacity"]).all()
    assert tr["patients"].sum() == 4                     # headroom 2 + 2
    assert t["unresolved_deficit"].sum() == 12 - 4 + 4 - 4  # 8 + 4 deficit, 4 placed
    c = city.iloc[0]
    assert c["unresolved_deficit"] == 8 and c["headroom_after"] == 0
    check_routing_invariants(t, tr)


def test_transfers_reconcile_and_city_totals_consistent():
    beds = _beds([("A", "A1", 7), ("A", "A2", 6), ("A", "A3", 0), ("A", "A4", 1)])
    cap = _cap([("A1", 3), ("A2", 3), ("A3", 3), ("A4", 4)])
    t, tr, city = route_overflow(beds, cap)
    out = tr.groupby("from_ward")["patients"].sum()
    for w, row in t.set_index("ward_id").iterrows():
        assert row["transferred_out"] == out.get(w, 0)
        assert row["deficit_before"] == row["transferred_out"] + row["unresolved_deficit"]
    c = city.iloc[0]
    assert c["bed_demand"] == c["beds_used_after"] + c["unresolved_deficit"]
    check_routing_invariants(t, tr)


def test_real_forecast_routing_is_intra_city_and_capacity_safe(system):
    from pipeline import run_plan
    for week in ("2024-08-12", "2025-06-23", "2025-06-02"):
        for h in ("2w", "4w"):
            r = run_plan(system, week, h, 70, 30, basis="cautious")
            check_routing_invariants(r["routing"], r["transfers"])


def test_deterministic_and_empty_and_malformed():
    beds = _beds([("A", "A1", 9), ("A", "A2", 1), ("A", "A3", 1)])
    cap = _cap([("A1", 5), ("A2", 4), ("A3", 4)])
    a = route_overflow(beds, cap)[1]
    b = route_overflow(beds.iloc[::-1], cap.iloc[::-1])[1]
    pd.testing.assert_frame_equal(a, b)
    t, tr, c = route_overflow(_beds([]), cap)
    assert tr.empty
    with pytest.raises(ValueError):
        route_overflow(_beds([("A", "A9", 3)]), cap)       # no capacity configured
    with pytest.raises(ValueError):
        route_overflow(beds, _cap([("A1", -1), ("A2", 4), ("A3", 4)]))


def test_demo_capacity_covers_all_60_wards(system):
    cap = system["capacity"]
    assert cap["ward_id"].nunique() == 60
    assert (cap["bed_capacity"] >= 1).all()
    assert (cap["source"] == "demo_assumption").all()
