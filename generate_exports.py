"""Regenerate the sample dispatch exports in /exports (runs fully offline).

Run:  python generate_exports.py [--week 2024-08-12] [--horizon 4w] [--stock 60] [--crews 40]
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from config import EXPORT_DIR  # noqa: E402
from dispatch_generator import html_brief, notices_for, pdf_brief, sms_text, whatsapp_text  # noqa: E402
from intervention_simulator import optimal_deployment, simulate  # noqa: E402
from pipeline import load_system, run_plan  # noqa: E402


def pick_examples(plan):
    """Representative wards: an overflow sender, a receiver, the top-priority ward and the lowest-priority ward."""
    picks = []
    for mask in (plan["transferred_out"] > 0, plan["transferred_in"] > 0,
                 plan["priority_rank"] == plan["priority_rank"].min(),
                 plan["priority_rank"] == plan["priority_rank"].max()):
        sub = plan[mask & ~plan["ward_id"].isin(picks)]
        if len(sub):
            picks.append(sub.sort_values("priority_rank")["ward_id"].iloc[0])
    return picks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", default="2024-08-12")
    ap.add_argument("--horizon", default="4w", choices=["2w", "4w"])
    ap.add_argument("--stock", type=int, default=60)
    ap.add_argument("--crews", type=int, default=40)
    a = ap.parse_args()

    EXPORT_DIR.mkdir(exist_ok=True)
    system = load_system()
    r = run_plan(system, a.week, a.horizon, a.stock, a.crews)
    plan, transfers = r["plan"], r["transfers"]
    examples = pick_examples(plan)
    notices = notices_for(plan.set_index("ward_id").loc[examples].reset_index(), transfers)
    header = (f"Scenario: data up to week of {a.week}, {a.horizon} horizon, regional stock {a.stock}%, "
              f"{a.crews} spraying crews. Wards: {', '.join(examples)}\n")

    (EXPORT_DIR / "sample_sms.txt").write_text(
        header + "\n" + "\n\n".join(f"[{n['ward_id']}] ({len(sms_text(n))} chars)\n{sms_text(n)}" for n in notices) + "\n")
    (EXPORT_DIR / "sample_whatsapp.txt").write_text(
        header + "\n" + "\n\n----------\n\n".join(whatsapp_text(n) for n in notices) + "\n", encoding="utf-8")

    city = plan.loc[plan["transferred_out"] > 0, "city"].iloc[0] if (plan["transferred_out"] > 0).any() else plan["city"].iloc[0]
    city_notices = notices_for(plan[plan["city"] == city].sort_values("priority_rank"), transfers)
    title = f"Commissioner dispatch brief: {city}"
    (EXPORT_DIR / "sample_commissioner_brief.html").write_text(html_brief(city_notices, title), encoding="utf-8")
    pdf = pdf_brief(city_notices, title)
    if pdf:
        (EXPORT_DIR / "sample_commissioner_brief.pdf").write_bytes(pdf)

    plan.to_csv(EXPORT_DIR / "dispatch_plan_all_wards.csv", index=False)
    transfers.to_csv(EXPORT_DIR / "bed_transfers.csv", index=False)
    r["city_beds"].to_csv(EXPORT_DIR / "city_bed_utilization.csv", index=False)

    fc = r["forecast"].rename(columns={f"risk_{a.horizon}": "risk"})
    deployment = optimal_deployment(fc, 20, a.horizon)
    sim, totals = simulate(fc, deployment, 20, r["rates"], a.horizon)
    sim.to_csv(EXPORT_DIR / "simulator_roi_ranking.csv", index=False)
    (EXPORT_DIR / "scenario.json").write_text(json.dumps({
        "week": a.week, "horizon": a.horizon, "stock_pct": a.stock, "total_crews": a.crews,
        "supply_summary": r["supply_summary"].to_dict("records"), "crews": r["crews"],
        "simulator_totals_20_crews_optimised": totals, "city_brief": city, "sample_wards": examples}, indent=2))
    print(header + f"Wrote exports to {EXPORT_DIR}")


if __name__ == "__main__":
    main()
