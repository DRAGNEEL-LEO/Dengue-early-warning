"""Offline kill-switch test.

Disables every network call in this Python process (socket connect, DNS lookup, HTTP via urllib/requests all
go through these), then runs the full operational chain: data load and validation, model loading, 2-week and
4-week forecasts, constrained allocation at several stock levels, intra-city bed routing, the vector-control
simulator and SMS / WhatsApp / HTML / PDF dispatch generation. Any attempt to reach the network raises.

Run:  python offline_check.py            (exit code 0 = passed; report written to exports/offline_check_report.txt)
For a physical test, also switch off Wi-Fi and run `streamlit run app.py` (see README).
"""
import socket
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

ATTEMPTS = []


def _blocked(*args, **kwargs):
    ATTEMPTS.append(repr(args[:2]))
    raise OSError("network disabled by offline kill-switch")


def kill_network():
    socket.socket.connect = _blocked
    socket.socket.connect_ex = _blocked
    socket.create_connection = _blocked
    socket.getaddrinfo = _blocked
    socket.gethostbyname = _blocked


def run_checks():
    from pipeline import load_system, run_plan
    from resource_allocation import check_allocation_invariants
    from hospital_routing import check_routing_invariants
    from intervention_simulator import simulate, optimal_deployment
    from dispatch_generator import notices_for, sms_text, whatsapp_text, html_brief, pdf_brief
    from system_status import internet_reachable

    log = []
    t0 = time.time()
    system = load_system()
    log.append(f"Loaded dataset ({system['report']['rows']} rows, {system['report']['wards']} wards, "
               f"{system['report']['cities']} cities), models and capacity table from local disk")
    weeks = ["2025-06-09", "2024-08-12", str(system["df"]["date"].max().date())]
    for week in weeks:
        for horizon in ("2w", "4w"):
            for pct in (100, 60, 30):
                r = run_plan(system, week, horizon, pct, total_crews=40)
                check_allocation_invariants(r["plan"], r["supply_summary"], r["crews"])
                check_routing_invariants(r["routing"], r["transfers"])
            fc = r["forecast"].rename(columns={f"risk_{horizon}": "risk"})
            plan = optimal_deployment(fc, 20, horizon)
            sim, tot = simulate(fc, plan, 20, r["rates"], horizon)
            assert tot["crews_assigned"] <= 20
            notices = notices_for(r["plan"], r["transfers"])
            assert len(notices) == 60
            sms_text(notices[0]), whatsapp_text(notices[0]), html_brief(notices[:5])
            pdf = pdf_brief(notices[:5])
            assert pdf is None or pdf[:4] == b"%PDF"
            log.append(f"{week} {horizon}: forecast, allocation (100/60/30% stock), routing "
                       f"({len(r['transfers'])} transfers), simulator ({tot['cases_prevented']} cases prevented), "
                       f"60 dispatch notices: OK")
    assert internet_reachable() is False, "status probe should report offline"
    log.append("Status probe correctly reports: internet unavailable")
    log.append(f"Blocked network attempts during run: {len(ATTEMPTS)} (all handled)")
    log.append(f"Total time: {time.time() - t0:.1f} s")
    return log


def main():
    kill_network()
    try:
        log = run_checks()
        ok = True
    except Exception:
        log = ["FAILED", traceback.format_exc()]
        ok = False
    report = "OFFLINE KILL-SWITCH TEST: " + ("PASSED" if ok else "FAILED") + "\n" + "\n".join(log) + "\n"
    print(report)
    out = ROOT / "exports" / "offline_check_report.txt"
    out.parent.mkdir(exist_ok=True)
    out.write_text(report)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
