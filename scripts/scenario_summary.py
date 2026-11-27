"""Print a one-screen planning summary for any scenario, from the command line (works fully offline).

Uses the same pipeline as the dashboard (src/pipeline.run_plan), so the numbers match the app exactly.

Examples:
    python scripts/scenario_summary.py
    python scripts/scenario_summary.py --week 2025-06-23 --horizon 4w --stock 40 --crews 20
    python scripts/scenario_summary.py --city "Dhaka South" --top 10
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from config import HORIZON_NAME, RESOURCE_LABEL, RESOURCES  # noqa: E402
from pipeline import load_system, run_plan  # noqa: E402

SHORT = {"saline_bags_needed": "Saline", "diagnostic_kits_needed": "Kits", "hospital_beds_required": "Beds"}


def main():
    ap = argparse.ArgumentParser(description="Dengue response scenario summary")
    ap.add_argument("--week", default="2024-08-12", help="forecast origin week (YYYY-MM-DD)")
    ap.add_argument("--horizon", default="2w", choices=["2w", "4w"])
    ap.add_argument("--stock", type=int, default=60, help="available regional stock, 30-100 (%%)")
    ap.add_argument("--crews", type=int, default=40, help="total spraying crews")
    ap.add_argument("--policy", default="weighted", choices=["weighted", "triage"])
    ap.add_argument("--city", default=None, help="limit the ward lists to one city")
    ap.add_argument("--top", type=int, default=5, help="number of priority wards to list")
    a = ap.parse_args()
    if not 30 <= a.stock <= 100:
        ap.error("--stock must be between 30 and 100")

    system = load_system()
    r = run_plan(system, a.week, a.horizon, a.stock, a.crews, a.policy)
    plan = r["plan"] if a.city is None else r["plan"][r["plan"]["city"] == a.city]
    if plan.empty:
        ap.error(f"no wards found for city {a.city!r}")

    print(f"\nScenario: data to {a.week}, planning week {r['target_week']:%Y-%m-%d} "
          f"({HORIZON_NAME[a.horizon]} ahead), stock {a.stock}%, {a.crews} crews, {a.policy} policy")
    print(f"Scope: {a.city or 'all cities'} ({len(plan)} wards)\n")

    print(f"{'Supply':<18}{'Required':>10}{'In stock':>10}{'Allocated':>11}{'Short by':>10}")
    for s in r["supply_summary"].itertuples():
        print(f"{RESOURCE_LABEL[s.resource]:<18}{s.required:>10}{s.available_stock:>10}{s.allocated:>11}"
              f"{s.deficit:>10}")
    c = r["crews"]
    print(f"{'Spraying crews':<18}{c['needed']:>10}{c['total']:>10}{c['assigned']:>11}{c['shortfall']:>10}")
    print("(supply totals are for the regional pool of all 60 wards)\n")

    tiers = plan["risk"].value_counts()
    print("Risk tiers: " + ", ".join(f"{t} {int(tiers.get(t, 0))}" for t in ("Critical", "High", "Medium", "Low")))
    print(f"Wards with a supply deficit: {int(plan['critical_deficit'].sum())}")
    print(f"Bed overflow: {int((plan['deficit_before'] > 0).sum())} ward(s), "
          f"{int(plan['transferred_out'].sum())} patient(s) moved within their city, "
          f"{int(plan['unresolved_deficit'].sum())} without a bed\n")

    print(f"Top {a.top} priority wards:")
    for w in plan.sort_values("priority_rank").head(a.top).itertuples():
        supplies = ", ".join(f"{SHORT[res]} {getattr(w, res + '_allocated')}/"
                             f"{getattr(w, res + '_required')}" for res in RESOURCES)
        print(f"  #{w.priority_rank:<3}{w.ward_id:<14}{w.city:<13}{w.risk:<9}{w.predicted_cases:>5.1f} cases  "
              f"{supplies}  crews {w.crews_assigned}/{w.crews_needed}")

    tr = r["transfers"]
    if a.city is not None and len(tr):
        tr = tr[tr["city"] == a.city]
    if len(tr):
        print("\nBed transfers (same city only):")
        for t in tr.itertuples():
            print(f"  {t.city}: {t.from_ward} -> {t.to_ward}  {t.patients} patient(s)")
    print()


if __name__ == "__main__":
    main()
