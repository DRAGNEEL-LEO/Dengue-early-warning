"""Hospital surge detection and intra-city overflow routing.

DATA LIMITATION: the dataset has no hospital bed capacity. data/ward_bed_capacity.csv is a DEMO ASSUMPTION
built by build_demo_capacity():
  * city pool  = 95th percentile of the city's total weekly hospital_beds_required in the training years
                 (2016-2023): a city sized for a bad, but not the worst, week;
  * ward share = the ward's share of the city's summed population density (assumes denser wards host more
                 facilities), rounded, minimum 1 bed.
Uniform per-ward capacities overflow everywhere at once in a peak week (forecast peaks are synchronised), so
nothing could be routed; uneven hospital distribution is the realistic case. The table is NOT verified hospital
capacity and must be replaced with real figures. The dashboard lets officers edit it.

Routing rule (deterministic, per city, never across cities):
  1. deficit_i = max(0, demand_i - capacity_i); headroom_i = max(0, capacity_i - demand_i)
  2. Sending wards are processed in descending deficit order (ties: ward_id).
  3. Each sending ward fills the receiving ward in the SAME city with the most remaining headroom
     (the lowest-burden ward; ties: ward_id), moves min(remaining deficit, headroom) patients, and repeats
     until its deficit is cleared or the city has no headroom left.
  4. Whatever cannot be placed stays as an unresolved city deficit.
"""
import math

import numpy as np
import pandas as pd

from config import CAPACITY_FILE, CAPACITY_MIN_BEDS, CAPACITY_QUANTILE, SPLIT_DATE

CAPACITY_NOTE = ("DEMO ASSUMPTION, not verified hospital capacity: each city's bed pool is the 95th percentile of "
                 "its weekly bed demand in 2016-2023, split across wards by population-density share.")


def build_demo_capacity(raw, split_date=SPLIT_DATE):
    train = raw[pd.to_datetime(raw["date"]) < pd.Timestamp(split_date)]
    weekly_city = train.groupby(["date", "city"])["hospital_beds_required"].sum().reset_index()
    pool = weekly_city.groupby("city")["hospital_beds_required"].quantile(CAPACITY_QUANTILE)
    dens = raw.groupby(["city", "ward_id"])["population_density_sqkm"].first().reset_index()
    dens["share"] = dens["population_density_sqkm"] / dens.groupby("city")["population_density_sqkm"].transform("sum")
    dens["bed_capacity"] = [max(CAPACITY_MIN_BEDS, int(math.floor(s * pool[c] + 0.5)))
                            for s, c in zip(dens["share"], dens["city"])]
    cap = dens[["city", "ward_id", "bed_capacity"]].copy()
    cap["source"] = "demo_assumption"
    return cap.sort_values(["city", "ward_id"]).reset_index(drop=True)


def load_capacity(path=CAPACITY_FILE, raw=None):
    """Read the capacity table; rebuild it from the data if the file is missing."""
    try:
        cap = pd.read_csv(path)
    except FileNotFoundError:
        if raw is None:
            raise
        cap = build_demo_capacity(raw)
    return cap


def route_overflow(wards, capacity):
    """wards: DataFrame with city, ward_id, beds_demand. capacity: DataFrame with ward_id, bed_capacity.

    Returns (ward_table, transfers, city_summary).
    """
    if wards.empty:
        empty_t = pd.DataFrame(columns=["city", "from_ward", "to_ward", "patients"])
        return wards.assign(bed_capacity=[], deficit_before=[], headroom_before=[], transferred_out=[],
                            transferred_in=[], beds_used_after=[], unresolved_deficit=[]), empty_t, pd.DataFrame()

    cap = capacity[["ward_id", "bed_capacity"]].copy()
    t = wards[["city", "ward_id", "beds_demand"]].merge(cap, on="ward_id", how="left")
    if t["bed_capacity"].isna().any():
        missing = t.loc[t["bed_capacity"].isna(), "ward_id"].tolist()
        raise ValueError(f"No bed capacity configured for wards: {missing}")
    if (t["bed_capacity"] < 0).any() or (t["beds_demand"] < 0).any():
        raise ValueError("Bed capacity and demand must be non-negative")
    t["bed_capacity"] = t["bed_capacity"].astype(int)
    t["beds_demand"] = t["beds_demand"].astype(int)
    t["deficit_before"] = (t["beds_demand"] - t["bed_capacity"]).clip(lower=0)
    t["headroom_before"] = (t["bed_capacity"] - t["beds_demand"]).clip(lower=0)
    t["transferred_out"] = 0
    t["transferred_in"] = 0

    transfers = []
    for city, grp in t.groupby("city", sort=True):
        deficit = dict(zip(grp["ward_id"], grp["deficit_before"]))
        headroom = dict(zip(grp["ward_id"], grp["headroom_before"]))
        senders = sorted((w for w, d in deficit.items() if d > 0), key=lambda w: (-deficit[w], w))
        for s in senders:
            need = deficit[s]
            while need > 0:
                receivers = [w for w, hr in headroom.items() if hr > 0 and w != s]
                if not receivers:
                    break
                r = min(receivers, key=lambda w: (-headroom[w], w))
                moved = min(need, headroom[r])
                headroom[r] -= moved
                need -= moved
                transfers.append({"city": city, "from_ward": s, "to_ward": r, "patients": int(moved)})
            deficit[s] = need

    tr = pd.DataFrame(transfers, columns=["city", "from_ward", "to_ward", "patients"])
    if not tr.empty:
        out = tr.groupby("from_ward")["patients"].sum()
        inn = tr.groupby("to_ward")["patients"].sum()
        t["transferred_out"] = t["ward_id"].map(out).fillna(0).astype(int)
        t["transferred_in"] = t["ward_id"].map(inn).fillna(0).astype(int)
    t["unresolved_deficit"] = t["deficit_before"] - t["transferred_out"]
    # Beds occupied in each ward after routing (a sending ward is full; a receiver adds incoming patients).
    t["beds_used_after"] = np.minimum(t["beds_demand"], t["bed_capacity"]) + t["transferred_in"]
    t["headroom_after"] = t["bed_capacity"] - t["beds_used_after"]
    t["status"] = np.select(
        [t["unresolved_deficit"] > 0, t["transferred_out"] > 0, t["transferred_in"] > 0],
        ["Overflow unresolved", "Overflow routed out", "Receiving transfers"], default="Within capacity")

    city = t.groupby("city").agg(
        wards=("ward_id", "count"), bed_demand=("beds_demand", "sum"), bed_capacity=("bed_capacity", "sum"),
        deficit_before=("deficit_before", "sum"), transferred=("transferred_out", "sum"),
        unresolved_deficit=("unresolved_deficit", "sum"), beds_used_after=("beds_used_after", "sum"),
    ).reset_index()
    cap_sum = city["bed_capacity"].replace(0, np.nan)
    city["utilization_before_pct"] = (100 * city["bed_demand"] / cap_sum).round(1).fillna(0)
    city["utilization_after_pct"] = (100 * city["beds_used_after"] / cap_sum).round(1).fillna(0)
    city["headroom_after"] = city["bed_capacity"] - city["beds_used_after"]
    return t, tr, city


def check_routing_invariants(ward_table, transfers):
    """Raise AssertionError if any routing guarantee is violated. Used by tests and the offline check."""
    city_of = dict(zip(ward_table["ward_id"], ward_table["city"]))
    for _, r in transfers.iterrows():
        assert city_of[r["from_ward"]] == city_of[r["to_ward"]] == r["city"], "cross-city transfer"
        assert r["patients"] > 0
    assert (ward_table["beds_used_after"] <= ward_table["bed_capacity"]).all(), "receiving capacity exceeded"
    assert (ward_table["transferred_out"] <= ward_table["deficit_before"]).all(), "moved more than the deficit"
    assert (ward_table["unresolved_deficit"] >= 0).all()
    # conservation: every patient in demand is either in a bed somewhere in the city or still unresolved
    for c, g in ward_table.groupby("city"):
        assert g["beds_demand"].sum() == g["beds_used_after"].sum() + g["unresolved_deficit"].sum(), c
    return True
