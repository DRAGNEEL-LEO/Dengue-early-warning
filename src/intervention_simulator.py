"""What-if vector-control simulator (larvicide / fogging crews).

SCIENTIFIC LIMITATION: the dataset contains no record of spraying or larviciding and no measured outcomes, so
intervention effectiveness cannot be learned from it. This module is a transparent counterfactual SCENARIO on
top of the ML forecast, not a causal estimate:

  baseline_h   = Random Forest forecast for the ward at horizon h (2 or 4 weeks)
  E(n)         = max_reduction * (1 - exp(-n / saturation_crews))     diminishing returns per extra crew
  prevented_h  = baseline_h * E(n) * timing_h                         timing_h: share of effect arrived by h
  simulated_h  = baseline_h - prevented_h
  bed / saline reduction = prevented_h * fitted per-case resource rate
  ROI          = prevented cases (selected horizon) / crews assigned

All parameters are visible in the UI and configurable (config.py). With zero crews E(0)=0, so nothing is
attributed to the intervention.

Why not perturb the model inputs instead? We tested lowering rainfall and water-logging inputs to mimic fewer
breeding sites and re-running the Random Forest. The response was not monotone (for some weeks it raised the
forecast in every ward), because the forest learned seasonal correlations, not a causal mosquito mechanism.
Scaling the forecast with an explicit, bounded effect curve is easier to defend and to audit.
"""
import numpy as np

from config import SIM_MAX_REDUCTION, SIM_SATURATION_CREWS, SIM_TIMING


def default_params():
    return {"max_reduction": SIM_MAX_REDUCTION, "saturation_crews": SIM_SATURATION_CREWS,
            "timing": dict(SIM_TIMING)}


def _validate_params(p):
    if not 0 <= p["max_reduction"] <= 1:
        raise ValueError("max_reduction must be between 0 and 1")
    if p["saturation_crews"] <= 0:
        raise ValueError("saturation_crews must be positive")
    for h, v in p["timing"].items():
        if not 0 <= v <= 1:
            raise ValueError(f"timing[{h}] must be between 0 and 1")


def effect(n_crews, params=None):
    """Share of forecast cases prevented at full timing by n crews (0 for n=0)."""
    p = params or default_params()
    n = np.asarray(n_crews, dtype=float)
    if (n < 0).any():
        raise ValueError("Crew counts cannot be negative")
    return p["max_reduction"] * (1 - np.exp(-n / p["saturation_crews"]))


def simulate(wards, deployment, available_crews, rates, horizon="2w", params=None):
    """wards: DataFrame with city, ward_id, risk, cases_2w, cases_4w (ML forecasts for the same origin week).
    deployment: {ward_id: crews}. Returns (ward_table sorted by ROI, totals dict)."""
    p = params or default_params()
    _validate_params(p)
    if horizon not in p["timing"]:
        raise ValueError(f"Unknown horizon {horizon!r}")
    deployment = {k: int(v) for k, v in (deployment or {}).items() if int(v) != 0}
    if any(v < 0 for v in deployment.values()):
        raise ValueError("Crew counts cannot be negative")
    unknown = set(deployment) - set(wards["ward_id"])
    if unknown:
        raise ValueError(f"Deployment names wards outside the selection: {sorted(unknown)}")
    used = sum(deployment.values())
    if used > available_crews:
        raise ValueError(f"{used} crews deployed but only {available_crews} available")

    t = wards[["city", "ward_id", "risk", "cases_2w", "cases_4w"]].copy()
    t["crews"] = t["ward_id"].map(deployment).fillna(0).astype(int)
    e = effect(t["crews"], p)
    raw = {}
    for h in ("2w", "4w"):
        base = t[f"cases_{h}"].clip(lower=0)
        raw[h] = base * e * p["timing"][h]
        t[f"simulated_{h}"] = (base - raw[h]).round(2)
        t[f"prevented_{h}"] = raw[h].round(2)
    sel = raw[horizon]                         # unrounded, so derived quantities are not double-rounded
    t["beds_reduction"] = (sel * rates["hospital_beds_required"]).round(2)
    t["saline_reduction"] = (sel * rates["saline_bags_needed"]).round(2)
    t["kits_reduction"] = (sel * rates["diagnostic_kits_needed"]).round(2)
    t["cases_prevented_per_crew"] = np.where(t["crews"] > 0, (sel / t["crews"].clip(lower=1)).round(3), 0.0)
    # What the FIRST crew would achieve in each ward: used to rank where crews should go next.
    t["first_crew_roi"] = (t[f"cases_{horizon}"].clip(lower=0) * float(effect(1, p)) * p["timing"][horizon]).round(3)
    t = t.sort_values(["cases_prevented_per_crew", "first_crew_roi", "ward_id"],
                      ascending=[False, False, True]).reset_index(drop=True)
    t["roi_rank"] = np.arange(1, len(t) + 1)

    totals = {
        "horizon": horizon, "crews_available": int(available_crews), "crews_assigned": int(used),
        "baseline_cases": round(float(t[f"cases_{horizon}"].clip(lower=0).sum()), 2),
        "simulated_cases": round(float(t[f"simulated_{horizon}"].sum()), 2),
        "cases_prevented": round(float(sel.sum()), 2),
        "beds_reduction": round(float(sel.sum() * rates["hospital_beds_required"]), 2),
        "saline_reduction": round(float(sel.sum() * rates["saline_bags_needed"]), 2),
        "cases_prevented_per_crew": round(float(sel.sum()) / used, 3) if used else 0.0,
        "prevented_2w": round(float(raw["2w"].sum()), 2),
        "prevented_4w": round(float(raw["4w"].sum()), 2),
    }
    return t, totals


def optimal_deployment(wards, available_crews, horizon="2w", params=None, max_per_ward=None):
    """Greedy marginal-gain deployment. Because E(n) is concave, giving each next crew to the ward with the
    largest marginal reduction maximises total prevented cases for this effect curve."""
    p = params or default_params()
    _validate_params(p)
    base = dict(zip(wards["ward_id"], wards[f"cases_{horizon}"].clip(lower=0)))
    plan = {w: 0 for w in base}
    timing = p["timing"][horizon]
    for _ in range(int(available_crews)):
        best, gain = None, 0.0
        for w in sorted(base):
            n = plan[w]
            if max_per_ward is not None and n >= max_per_ward:
                continue
            g = base[w] * timing * float(effect(n + 1, p) - effect(n, p))
            if g > gain + 1e-12:
                best, gain = w, g
        if best is None:
            break
        plan[best] += 1
    return {w: n for w, n in plan.items() if n > 0}

