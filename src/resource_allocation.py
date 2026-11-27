"""Constrained resource allocation under scarcity.

Inputs per ward: forecast cases, risk tier, population density and integer demand for each resource.
Controls: Available Regional Stock (30-100 % of total forecast demand), total spraying crews, policy.

Priority score (configurable assumption, not official policy):
    priority = w_risk * risk_score(tier) + w_density * density_norm
  risk_score: Low 0, Medium 1/3, High 2/3, Critical 1
  density_norm: (density - min) / (max - min) over all 60 wards (min-max scaled, 0..1)
  Ties are broken by forecast cases (higher first), then ward_id, so results are fully deterministic.

Policies for each supply (saline, kits, beds):
  "weighted" (default): priority-weighted water-filling. Each ward receives the share
        fill_i = min(1, lambda * p_i) of its demand, where p_i = max(priority_i, floor) and lambda is set by
        bisection so the total equals the available stock. Higher-priority wards get a larger share, top wards
        are filled completely first, and lower-priority wards are reduced rather than cut to zero.
  "triage": strict priority order. Fully satisfy the highest-priority ward, then the next, until stock runs out.
Fractional results are converted to whole units with the largest-remainder rule (priority order on ties),
so totals never exceed stock and no ward ever receives more than it needs.

Spraying crews: each ward needs CREWS_NEEDED_BY_TIER[tier]. Crews are dealt one at a time in rounds, in
priority order (round 1 gives every ward that needs a crew its first crew, highest priority first; round 2 the
second, ...). This spreads coverage before stacking crews in a single ward.
"""
import math

import numpy as np
import pandas as pd

from config import (CREWS_NEEDED_BY_TIER, PRIORITY_FLOOR, PRIORITY_WEIGHTS, RESOURCES, RISK_SCORE)

POLICIES = ("weighted", "triage")


def priority_scores(wards, weights=None, density_range=None):
    """Add risk_score, density_norm, priority and priority_rank columns."""
    weights = dict(PRIORITY_WEIGHTS if weights is None else weights)
    if any(v < 0 for v in weights.values()):
        raise ValueError("Priority weights must be non-negative")
    total = weights.get("risk", 0) + weights.get("density", 0)
    if total <= 0:
        raise ValueError("At least one priority weight must be positive")
    w_risk, w_den = weights.get("risk", 0) / total, weights.get("density", 0) / total

    out = wards.copy()
    unknown = set(out["risk"]) - set(RISK_SCORE)
    if unknown:
        raise ValueError(f"Unknown risk tiers: {unknown}")
    out["risk_score"] = out["risk"].map(RISK_SCORE).astype(float)
    lo, hi = density_range if density_range else (out["population_density_sqkm"].min(),
                                                  out["population_density_sqkm"].max())
    span = hi - lo
    out["density_norm"] = 0.0 if span <= 0 else ((out["population_density_sqkm"] - lo) / span).clip(0, 1)
    out["priority"] = (w_risk * out["risk_score"] + w_den * out["density_norm"]).round(6)
    out = out.sort_values(["priority", "predicted_cases", "ward_id"], ascending=[False, False, True])
    out["priority_rank"] = np.arange(1, len(out) + 1)
    return out.reset_index(drop=True)


def available_stock(total_demand, stock_pct):
    if not 0 <= stock_pct <= 100:
        raise ValueError("stock_pct must be between 0 and 100")
    return int(math.floor(round(total_demand * stock_pct / 100.0, 6)))


def _integerize(cont, demand, stock, order):
    """Largest-remainder rounding. cont: continuous allocation (sum <= stock, cont <= demand)."""
    alloc = np.floor(cont + 1e-9).astype(int)
    alloc = np.minimum(alloc, demand)
    left = stock - int(alloc.sum())
    if left > 0:
        frac = cont - alloc
        # candidates that can still take a unit, by largest remainder then priority order
        cand = sorted((i for i in range(len(demand)) if alloc[i] < demand[i]),
                      key=lambda i: (-round(frac[i], 9), order[i]))
        for i in cand:
            if left == 0:
                break
            alloc[i] += 1
            left -= 1
        for i in order:                       # numerical safety net: top up in priority order
            if left == 0:
                break
            give = min(int(demand[i] - alloc[i]), left)
            alloc[i] += give
            left -= give
    return alloc


def allocate_supply(demand, priority, stock, policy="weighted"):
    """Allocate one resource. demand, priority: arrays in priority order (rank 1 first)."""
    demand = np.asarray(demand, dtype=int)
    if (demand < 0).any():
        raise ValueError("Demand cannot be negative")
    if stock < 0:
        raise ValueError("Stock cannot be negative")
    n = len(demand)
    total = int(demand.sum())
    if n == 0:
        return demand.copy()
    if stock >= total:
        return demand.copy()
    order = np.arange(n)
    if policy == "triage":
        alloc = np.zeros(n, dtype=int)
        left = stock
        for i in order:
            give = min(int(demand[i]), left)
            alloc[i] = give
            left -= give
        return alloc
    if policy != "weighted":
        raise ValueError(f"Unknown policy {policy!r}; use one of {POLICIES}")

    p = np.maximum(np.asarray(priority, dtype=float), PRIORITY_FLOOR)

    def filled(lam):
        return np.minimum(demand, lam * p * demand)

    lo, hi = 0.0, 1.0 / p.min()
    for _ in range(100):                     # bisection: sum(filled) is monotone in lambda
        mid = (lo + hi) / 2
        if filled(mid).sum() > stock:
            hi = mid
        else:
            lo = mid
    return _integerize(filled(lo), demand, stock, order)


def allocate_crews(crews_needed, total_crews):
    """Round-robin by priority. crews_needed must be in priority order."""
    if total_crews < 0:
        raise ValueError("Total crews cannot be negative")
    need = np.asarray(crews_needed, dtype=int)
    got = np.zeros(len(need), dtype=int)
    left = int(total_crews)
    rnd = 1
    while left > 0 and (got < need).any():
        for i in range(len(need)):
            if left == 0:
                break
            if need[i] >= rnd:
                got[i] += 1
                left -= 1
        rnd += 1
    return got


def run_allocation(wards, stock_pct=100, total_crews=0, policy="weighted", weights=None, density_range=None):
    """Full allocation for a set of wards.

    wards needs: city, ward_id, population_density_sqkm, predicted_cases, risk and one column per resource
    (the integer demand). Returns (ward_table, summary_by_resource, crew_summary).
    """
    if wards.empty:
        return wards.copy(), pd.DataFrame(), {"total": int(total_crews), "needed": 0, "assigned": 0, "idle": int(total_crews)}
    t = priority_scores(wards, weights, density_range)
    rows = []
    for r in RESOURCES:
        demand = t[r].to_numpy(dtype=int)
        total = int(demand.sum())
        stock = available_stock(total, stock_pct)
        alloc = allocate_supply(demand, t["priority"].to_numpy(), stock, policy)
        t[f"{r}_required"] = demand
        t[f"{r}_allocated"] = alloc
        t[f"{r}_deficit"] = demand - alloc
        t[f"{r}_fill_pct"] = np.where(demand > 0, np.round(100 * alloc / np.maximum(demand, 1), 1), 100.0)
        rows.append({"resource": r, "required": total, "available_stock": stock, "allocated": int(alloc.sum()),
                     "deficit": int((demand - alloc).sum()), "wards_short": int(((demand - alloc) > 0).sum())})
    t = t.drop(columns=list(RESOURCES))

    t["crews_needed"] = t["risk"].map(CREWS_NEEDED_BY_TIER).astype(int)
    t["crews_assigned"] = allocate_crews(t["crews_needed"].to_numpy(), total_crews)
    t["crews_deficit"] = t["crews_needed"] - t["crews_assigned"]

    deficit_cols = [f"{r}_deficit" for r in RESOURCES]
    t["supply_deficit_units"] = t[deficit_cols].sum(axis=1)
    t["critical_deficit"] = t["supply_deficit_units"] > 0
    t["alert"] = np.where(t["critical_deficit"], "CRITICAL SUPPLY DEFICIT", "Fully supplied")

    summary = pd.DataFrame(rows)
    crews = {"total": int(total_crews), "needed": int(t["crews_needed"].sum()),
             "assigned": int(t["crews_assigned"].sum()),
             "idle": int(total_crews - t["crews_assigned"].sum()),
             "shortfall": int(t["crews_deficit"].sum())}
    return t, summary, crews


def check_allocation_invariants(table, summary, crews):
    for _, s in summary.iterrows():
        r = s["resource"]
        assert table[f"{r}_allocated"].sum() <= s["available_stock"], f"{r}: allocated exceeds stock"
        assert (table[f"{r}_allocated"] >= 0).all(), f"{r}: negative allocation"
        assert (table[f"{r}_allocated"] <= table[f"{r}_required"]).all(), f"{r}: over-allocation"
        assert (table[f"{r}_deficit"] == table[f"{r}_required"] - table[f"{r}_allocated"]).all()
    assert table["crews_assigned"].sum() <= crews["total"], "crews exceed available"
    assert (table["crews_assigned"] <= table["crews_needed"]).all()
    return True
