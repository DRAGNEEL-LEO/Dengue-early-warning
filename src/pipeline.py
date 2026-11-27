"""One call that runs the whole operational chain locally:
forecast -> resource demand -> constrained allocation -> hospital overflow routing -> dispatch-ready table.

Used by the dashboard, the export script, the offline kill-switch check and the tests, so all of them exercise
exactly the same code path.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from config import DATA, HORIZON_WEEKS, RESOURCES
from data_processing import load_dataset
from features import build_features
from hospital_routing import load_capacity, route_overflow
from predict import forecast_wards, load_models
from resource_allocation import run_allocation
from resource_demand import demand_from_cases


def load_system(data_path=DATA):
    """Everything the system needs, read from local files only."""
    raw, report = load_dataset(data_path)
    df = build_features(raw)
    models, meta = load_models()
    capacity = load_capacity(raw=raw)
    return {"raw": raw, "df": df, "models": models, "meta": meta, "capacity": capacity, "report": report}


def latest_week(df):
    return df["date"].max()


def run_plan(system, date=None, horizon="2w", stock_pct=100, total_crews=60, policy="weighted",
             basis="expected", capacity=None, weights=None):
    df, models, meta = system["df"], system["models"], system["meta"]
    date = pd.Timestamp(date) if date is not None else latest_week(df)
    capacity = system["capacity"] if capacity is None else capacity
    rates = meta["resource_rates"]

    fc = forecast_wards(models, meta, df, date, basis=basis)
    wards = fc[["city", "ward_id", "population_density_sqkm"]].copy()
    wards["predicted_cases"] = fc[f"cases_{horizon}"]
    wards["risk"] = fc[f"risk_{horizon}"]
    for r, v in demand_from_cases(wards["predicted_cases"], rates).items():
        wards[r] = v

    density = system["raw"].groupby("ward_id")["population_density_sqkm"].first()
    alloc, summary, crews = run_allocation(wards, stock_pct, total_crews, policy, weights,
                                           density_range=(density.min(), density.max()))

    beds = alloc[["city", "ward_id"]].copy()
    beds["beds_demand"] = alloc["hospital_beds_required_required"]
    routing, transfers, city_beds = route_overflow(beds, capacity)

    target_week = date + pd.Timedelta(weeks=HORIZON_WEEKS[horizon])
    plan = alloc.merge(routing.drop(columns=["city", "beds_demand"]), on="ward_id", how="left")
    plan.insert(0, "forecast_origin_week", date.strftime("%Y-%m-%d"))
    plan.insert(1, "target_week", target_week.strftime("%Y-%m-%d"))
    plan.insert(2, "horizon", horizon)
    return {
        "date": date, "target_week": target_week, "horizon": horizon, "stock_pct": stock_pct,
        "total_crews": total_crews, "policy": policy, "basis": basis,
        "forecast": fc, "plan": plan, "supply_summary": summary, "crews": crews,
        "routing": routing, "transfers": transfers, "city_beds": city_beds, "rates": rates,
        "resources": RESOURCES,
    }
