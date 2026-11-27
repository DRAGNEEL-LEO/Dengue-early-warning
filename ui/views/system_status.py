import importlib.metadata as md
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

from ui import components as C
from ui import theme as T
from ui.state import ctx

ROOT = Path(__file__).resolve().parents[2]
c = ctx()
meta, rep = c.meta, c.system["report"]
from system_status import local_checks  # noqa: E402

checks = local_checks()
missing = [r for r in checks if r["status"] == "MISSING"]
C.page_header("System status", "What is loaded, what runs locally, and how to prove it works without the internet.")

C.kpi_row([
    dict(label="Application", value="Running", foot="Streamlit, local process", accent=T.GREEN),
    dict(label="Models", value="Loaded", foot="2-week and 4-week forests",
         accent=T.GREEN),
    dict(label="Dataset", value=f"{rep['rows']:,}", unit="rows",
         foot=f"{rep['wards']} wards · {rep['cities']} cities · {rep['missing_values']} missing", accent=T.GREEN),
    dict(label="Offline capability", value="5 / 5", foot="core functions need no internet", accent=T.BLUE),
    dict(label="Internet", value="Available" if c.online else "Offline", foot="probe only, never required",
         accent=T.CYAN if c.online else T.ORANGE),
])
if missing:
    C.alert("critical", "Missing local files", ", ".join(r["component"] for r in missing))

left, right = st.columns([1.25, 1], gap="medium")
with left:
    with C.card():
        st.markdown("**Modules**")
        mods = pd.DataFrame([
            ("Forecasting (2 and 4 weeks)", "src/predict.py", "Available"),
            ("Resource-demand estimation", "src/resource_demand.py", "Available"),
            ("Constrained resource allocation", "src/resource_allocation.py", "Available"),
            ("Intra-city hospital routing", "src/hospital_routing.py", "Available"),
            ("Intervention simulator", "src/intervention_simulator.py", "Available"),
            ("Dispatch generation (SMS, WhatsApp, HTML, PDF)", "src/dispatch_generator.py",
             "Available" if any(r["component"].startswith("PDF") and r["status"] == "OK" for r in checks)
             else "Available (HTML only)"),
            ("SMS / WhatsApp delivery gateway", "not implemented", "Not connected"),
            ("External APIs / LLM", "not used", "Not used"),
        ], columns=["Module", "Code", "Status"])
        st.dataframe(mods.style.map(lambda v: "color:#15803D;font-weight:600" if str(v).startswith("Available")
                                    else "color:#64748B;font-weight:600", subset=["Status"]),
                     hide_index=True, width="stretch")
    with C.card():
        st.markdown("**Local files**")
        st.dataframe(pd.DataFrame(checks), hide_index=True, width="stretch",
                     column_config={"component": "Component", "status": "Status", "detail": "Detail"})
with right:
    with C.card():
        st.markdown("**Offline kill-switch self-test**")
        st.caption("Runs offline_check.py in a separate process with every socket and DNS call disabled, then "
                   "exercises forecasting, allocation, routing, the simulator and all dispatch formats.")
        if st.button("Run offline self-test", type="primary", icon=":material/wifi_off:"):
            with st.spinner("Running with the network disabled..."):
                res = subprocess.run([sys.executable, str(ROOT / "offline_check.py")], capture_output=True,
                                     text=True, timeout=600)
            if res.returncode == 0:
                C.alert("ok", "Offline self-test passed", "All core workflows ran with the network disabled.")
            else:
                C.alert("critical", "Offline self-test failed", "See the log below.")
            st.code(res.stdout[-4000:] + res.stderr[-2000:], language=None)
    with C.card():
        st.markdown("**Dependencies**")
        rows = []
        for pkg in ("streamlit", "pandas", "numpy", "scikit-learn", "joblib", "plotly", "altair", "fpdf2"):
            try:
                rows.append((pkg, md.version(pkg), "Installed"))
            except md.PackageNotFoundError:
                rows.append((pkg, "-", "Not installed (optional)" if pkg in ("fpdf2", "altair") else "Missing"))
        rows.append(("Python", sys.version.split()[0], "Running"))
        st.dataframe(pd.DataFrame(rows, columns=["Package", "Version", "Status"]), hide_index=True, width="stretch")
    with C.card():
        st.markdown("**Data window**")
        C.kv_list([("First week", rep["first_week"]), ("Last week", rep["last_week"]),
                   ("Training years", f"2016 to {int(meta['split_date'][:4]) - 1}"),
                   ("Held-out test from", meta["split_date"]), ("Duplicate rows", rep["duplicate_rows"])])
